import pathlib
import sys
from typing import (
    Generator,
    List,
    Set,
    Tuple,
    Union,
)

from aristaproto.lib.google.protobuf import (
    DescriptorProto,
    EnumDescriptorProto,
    FieldDescriptorProto,
    FileDescriptorProto,
    ServiceDescriptorProto,
)
from aristaproto.lib.google.protobuf.compiler import (
    CodeGeneratorRequest,
    CodeGeneratorResponse,
    CodeGeneratorResponseFeature,
    CodeGeneratorResponseFile,
)

from .compiler import outputfile_compiler
from .models import (
    EnumDefinitionCompiler,
    FieldCompiler,
    MapEntryCompiler,
    MessageCompiler,
    OneOfFieldCompiler,
    OutputTemplate,
    PluginRequestCompiler,
    PydanticOneOfFieldCompiler,
    ServiceCompiler,
    ServiceMethodCompiler,
    is_map,
    is_oneof,
)
from .typing_compiler import (
    DirectImportTypingCompiler,
    NoTyping310TypingCompiler,
    TypingImportTypingCompiler,
)


def traverse(
    proto_file: FileDescriptorProto,
) -> Generator[
    Tuple[Union[EnumDescriptorProto, DescriptorProto], List[int]], None, None
]:
    # Todo: Keep information about nested hierarchy
    def _traverse(
        path: List[int],
        items: Union[List[EnumDescriptorProto], List[DescriptorProto]],
        prefix: str = "",
    ) -> Generator[
        Tuple[Union[EnumDescriptorProto, DescriptorProto], List[int]], None, None
    ]:
        for i, item in enumerate(items):
            # Adjust the name since we flatten the hierarchy.
            # Todo: don't change the name, but include full name in returned tuple
            item.name = next_prefix = f"{prefix}_{item.name}"
            yield item, [*path, i]

            if isinstance(item, DescriptorProto):
                # Get nested types.
                yield from _traverse([*path, i, 4], item.enum_type, next_prefix)
                yield from _traverse([*path, i, 3], item.nested_type, next_prefix)

    yield from _traverse([5], proto_file.enum_type)
    yield from _traverse([4], proto_file.message_type)


def generate_code(request: CodeGeneratorRequest) -> CodeGeneratorResponse:
    response = CodeGeneratorResponse()

    plugin_options = request.parameter.split(",") if request.parameter else []
    response.supported_features = CodeGeneratorResponseFeature.FEATURE_PROTO3_OPTIONAL

    request_data = PluginRequestCompiler(plugin_request_obj=request)
    # Gather output packages
    for proto_file in request.proto_file:
        output_package_name = proto_file.package
        if output_package_name not in request_data.output_packages:
            # Create a new output if there is no output for this package
            request_data.output_packages[output_package_name] = OutputTemplate(
                parent_request=request_data, package_proto_obj=proto_file
            )
        # Add this input file to the output corresponding to this package
        request_data.output_packages[output_package_name].input_files.append(proto_file)

        if (
            proto_file.package == "google.protobuf"
            and "INCLUDE_GOOGLE" not in plugin_options
        ):
            # If not INCLUDE_GOOGLE,
            # skip outputting Google's well-known types
            request_data.output_packages[output_package_name].output = False

        if "pydantic_dataclasses" in plugin_options:
            request_data.output_packages[
                output_package_name
            ].pydantic_dataclasses = True

        # Gather any typing generation options.
        typing_opts = [
            opt[len("typing.") :] for opt in plugin_options if opt.startswith("typing.")
        ]

        if len(typing_opts) > 1:
            raise ValueError("Multiple typing options provided")
        # Set the compiler type.
        typing_opt = typing_opts[0] if typing_opts else "direct"
        if typing_opt == "direct":
            request_data.output_packages[
                output_package_name
            ].typing_compiler = DirectImportTypingCompiler()
        elif typing_opt == "root":
            request_data.output_packages[
                output_package_name
            ].typing_compiler = TypingImportTypingCompiler()
        elif typing_opt == "310":
            request_data.output_packages[
                output_package_name
            ].typing_compiler = NoTyping310TypingCompiler()

    # Read Messages and Enums
    # We need to read Messages before Services in so that we can
    # get the references to input/output messages for each service
    for output_package_name, output_package in request_data.output_packages.items():
        for proto_input_file in output_package.input_files:
            for item, path in traverse(proto_input_file):
                read_protobuf_type(
                    source_file=proto_input_file,
                    item=item,
                    path=path,
                    output_package=output_package,
                )

    # Read Services
    for output_package_name, output_package in request_data.output_packages.items():
        for proto_input_file in output_package.input_files:
            for index, service in enumerate(proto_input_file.service):
                read_protobuf_service(proto_input_file, service, index, output_package)

    # Generate output files
    output_paths: Set[pathlib.Path] = set()
    for output_package_name, output_package in request_data.output_packages.items():
        if not output_package.output:
            continue

        # Add files to the response object
        output_path = pathlib.Path(*output_package_name.split("."), "__init__.py")
        output_paths.add(output_path)

        response.file.append(
            CodeGeneratorResponseFile(
                name=str(output_path),
                # Render and then format the output file
                content=outputfile_compiler(output_file=output_package),
            )
        )

    # Make each output directory a package with __init__ file
    init_files = {
        directory.joinpath("__init__.py")
        for path in output_paths
        for directory in path.parents
        if not directory.joinpath("__init__.py").exists()
    } - output_paths

    for init_file in init_files:
        response.file.append(CodeGeneratorResponseFile(name=str(init_file)))

    for output_package_name in sorted(output_paths.union(init_files)):
        print(f"Writing {output_package_name}", file=sys.stderr)

    return response


def _make_one_of_field_compiler(
    output_package: OutputTemplate,
    source_file: "FileDescriptorProto",
    parent: MessageCompiler,
    proto_obj: "FieldDescriptorProto",
    path: List[int],
) -> FieldCompiler:
    pydantic = output_package.pydantic_dataclasses
    Cls = PydanticOneOfFieldCompiler if pydantic else OneOfFieldCompiler
    return Cls(
        source_file=source_file,
        parent=parent,
        proto_obj=proto_obj,
        path=path,
        typing_compiler=output_package.typing_compiler,
    )


def read_protobuf_type(
    item: DescriptorProto,
    path: List[int],
    source_file: "FileDescriptorProto",
    output_package: OutputTemplate,
) -> None:
    if isinstance(item, DescriptorProto):
        if item.options.map_entry:
            # Skip generated map entry messages since we just use dicts
            return
        # Process Message
        message_data = MessageCompiler(
            source_file=source_file,
            parent=output_package,
            proto_obj=item,
            path=path,
            typing_compiler=output_package.typing_compiler,
        )
        for index, field in enumerate(item.field):
            if is_map(field, item):
                MapEntryCompiler(
                    source_file=source_file,
                    parent=message_data,
                    proto_obj=field,
                    path=path + [2, index],
                    typing_compiler=output_package.typing_compiler,
                )
            elif is_oneof(field):
                _make_one_of_field_compiler(
                    output_package, source_file, message_data, field, path + [2, index]
                )
            else:
                FieldCompiler(
                    source_file=source_file,
                    parent=message_data,
                    proto_obj=field,
                    path=path + [2, index],
                    typing_compiler=output_package.typing_compiler,
                )
    elif isinstance(item, EnumDescriptorProto):
        # Enum
        EnumDefinitionCompiler(
            source_file=source_file,
            parent=output_package,
            proto_obj=item,
            path=path,
            typing_compiler=output_package.typing_compiler,
        )


def read_protobuf_service(
    source_file: FileDescriptorProto,
    service: ServiceDescriptorProto,
    index: int,
    output_package: OutputTemplate,
) -> None:
    service_data = ServiceCompiler(
        source_file=source_file,
        parent=output_package,
        proto_obj=service,
        path=[6, index],
    )
    for j, method in enumerate(service.method):
        ServiceMethodCompiler(
            source_file=source_file,
            parent=service_data,
            proto_obj=method,
            path=[6, index, 2, j],
        )
