"""Plugin model dataclasses.

These classes are meant to be an intermediate representation
of protobuf objects. They are used to organize the data collected during parsing.

The general intention is to create a doubly-linked tree-like structure
with the following types of references:
- Downwards references: from message -> fields, from output package -> messages
or from service -> service methods
- Upwards references: from field -> message, message -> package.
- Input/output message references: from a service method to it's corresponding
input/output messages, which may even be in another package.

There are convenience methods to allow climbing up and down this tree, for
example to retrieve the list of all messages that are in the same package as
the current message.

Most of these classes take as inputs:
- proto_obj: A reference to it's corresponding protobuf object as
presented by the protoc plugin.
- parent: a reference to the parent object in the tree.

With this information, the class is able to expose attributes,
such as a pythonized name, that will be calculated from proto_obj.

The instantiation should also attach a reference to the new object
into the corresponding place within it's parent object. For example,
instantiating field `A` with parent message `B` should add a
reference to `A` to `B`'s `fields` attribute.
"""

import builtins
import re
from dataclasses import (
    dataclass,
    field,
)
from typing import (
    Dict,
    Iterable,
    Iterator,
    List,
    Optional,
    Set,
    Type,
    Union,
)

import aristaproto
from aristaproto.lib.google.protobuf import (
    DescriptorProto,
    EnumDescriptorProto,
    Field,
    FieldDescriptorProto,
    FieldDescriptorProtoLabel,
    FieldDescriptorProtoType,
    FileDescriptorProto,
    MethodDescriptorProto,
)
from aristaproto.lib.google.protobuf.compiler import CodeGeneratorRequest

from .. import which_one_of
from ..compile.importing import (
    get_type_reference,
)
from ..compile.naming import (
    pythonize_class_name,
    pythonize_enum_member_name,
    pythonize_field_name,
    pythonize_method_name,
)
from .typing_compiler import (
    DirectImportTypingCompiler,
    TypingCompiler,
)


# Create a unique placeholder to deal with
# https://stackoverflow.com/questions/51575931/class-inheritance-in-python-3-7-dataclasses
PLACEHOLDER = object()

# Organize proto types into categories
PROTO_FLOAT_TYPES = (
    FieldDescriptorProtoType.TYPE_DOUBLE,  # 1
    FieldDescriptorProtoType.TYPE_FLOAT,  # 2
)
PROTO_INT_TYPES = (
    FieldDescriptorProtoType.TYPE_INT64,  # 3
    FieldDescriptorProtoType.TYPE_UINT64,  # 4
    FieldDescriptorProtoType.TYPE_INT32,  # 5
    FieldDescriptorProtoType.TYPE_FIXED64,  # 6
    FieldDescriptorProtoType.TYPE_FIXED32,  # 7
    FieldDescriptorProtoType.TYPE_UINT32,  # 13
    FieldDescriptorProtoType.TYPE_SFIXED32,  # 15
    FieldDescriptorProtoType.TYPE_SFIXED64,  # 16
    FieldDescriptorProtoType.TYPE_SINT32,  # 17
    FieldDescriptorProtoType.TYPE_SINT64,  # 18
)
PROTO_BOOL_TYPES = (FieldDescriptorProtoType.TYPE_BOOL,)  # 8
PROTO_STR_TYPES = (FieldDescriptorProtoType.TYPE_STRING,)  # 9
PROTO_BYTES_TYPES = (FieldDescriptorProtoType.TYPE_BYTES,)  # 12
PROTO_MESSAGE_TYPES = (
    FieldDescriptorProtoType.TYPE_MESSAGE,  # 11
    FieldDescriptorProtoType.TYPE_ENUM,  # 14
)
PROTO_MAP_TYPES = (FieldDescriptorProtoType.TYPE_MESSAGE,)  # 11
PROTO_PACKED_TYPES = (
    FieldDescriptorProtoType.TYPE_DOUBLE,  # 1
    FieldDescriptorProtoType.TYPE_FLOAT,  # 2
    FieldDescriptorProtoType.TYPE_INT64,  # 3
    FieldDescriptorProtoType.TYPE_UINT64,  # 4
    FieldDescriptorProtoType.TYPE_INT32,  # 5
    FieldDescriptorProtoType.TYPE_FIXED64,  # 6
    FieldDescriptorProtoType.TYPE_FIXED32,  # 7
    FieldDescriptorProtoType.TYPE_BOOL,  # 8
    FieldDescriptorProtoType.TYPE_UINT32,  # 13
    FieldDescriptorProtoType.TYPE_SFIXED32,  # 15
    FieldDescriptorProtoType.TYPE_SFIXED64,  # 16
    FieldDescriptorProtoType.TYPE_SINT32,  # 17
    FieldDescriptorProtoType.TYPE_SINT64,  # 18
)


def monkey_patch_oneof_index():
    """
    The compiler message types are written for proto2, but we read them as proto3.
    For this to work in the case of the oneof_index fields, which depend on being able
    to tell whether they were set, we have to treat them as oneof fields. This method
    monkey patches the generated classes after the fact to force this behaviour.
    """
    object.__setattr__(
        FieldDescriptorProto.__dataclass_fields__["oneof_index"].metadata[
            "aristaproto"
        ],
        "group",
        "oneof_index",
    )
    object.__setattr__(
        Field.__dataclass_fields__["oneof_index"].metadata["aristaproto"],
        "group",
        "oneof_index",
    )


def get_comment(
    proto_file: "FileDescriptorProto", path: List[int], indent: int = 4
) -> str:
    pad = " " * indent
    for sci_loc in proto_file.source_code_info.location:
        if list(sci_loc.path) == path:
            all_comments = list(sci_loc.leading_detached_comments)
            if sci_loc.leading_comments:
                all_comments.append(sci_loc.leading_comments)
            if sci_loc.trailing_comments:
                all_comments.append(sci_loc.trailing_comments)

            lines: list[str] = []

            for comment in all_comments:
                lines += comment.split("\n")
                lines.append("")

            # Remove consecutive empty lines
            lines = [
                line for i, line in enumerate(lines) if line or (i == 0 or lines[i - 1])
            ]

            if lines and not lines[-1]:
                lines.pop()  # Remove the last empty line

            # It is common for one line comments to start with a space, for example: // comment
            # We don't add this space to the generated file.
            lines = [line[1:] if line and line[0] == " " else line for line in lines]

            # Escape any double-quotes to avoid interference with docstring quotes.
            lines = [line.replace('"', '\\"') for line in lines]

            # This is a field, message, enum, service, or method
            if len(lines) == 1 and len(lines[0]) < 79 - indent - 6:
                return f'{pad}"""{lines[0]}"""'
            else:
                # rstrip to remove trailing spaces including empty lines.
                padded = [f"\n{pad}{line}".rstrip(" ") for line in lines]
                joined = "".join(padded)
                return f'{pad}"""{joined}\n{pad}"""'

    return ""


class ProtoContentBase:
    """Methods common to MessageCompiler, ServiceCompiler and ServiceMethodCompiler."""

    source_file: FileDescriptorProto
    typing_compiler: TypingCompiler
    path: List[int]
    comment_indent: int = 4
    parent: Union["aristaproto.Message", "OutputTemplate"]

    __dataclass_fields__: Dict[str, object]

    def __post_init__(self) -> None:
        """Checks that no fake default fields were left as placeholders."""
        for field_name, field_val in self.__dataclass_fields__.items():
            if field_val is PLACEHOLDER:
                raise ValueError(f"`{field_name}` is a required field.")

    @property
    def output_file(self) -> "OutputTemplate":
        current = self
        while not isinstance(current, OutputTemplate):
            current = current.parent
        return current

    @property
    def request(self) -> "PluginRequestCompiler":
        current = self
        while not isinstance(current, OutputTemplate):
            current = current.parent
        return current.parent_request

    @property
    def comment(self) -> str:
        """Crawl the proto source code and retrieve comments
        for this object.
        """
        return get_comment(
            proto_file=self.source_file, path=self.path, indent=self.comment_indent
        )


@dataclass
class PluginRequestCompiler:
    plugin_request_obj: CodeGeneratorRequest
    output_packages: Dict[str, "OutputTemplate"] = field(default_factory=dict)

    @property
    def all_messages(self) -> List["MessageCompiler"]:
        """All of the messages in this request.

        Returns
        -------
        List[MessageCompiler]
            List of all of the messages in this request.
        """
        return [
            msg for output in self.output_packages.values() for msg in output.messages
        ]


@dataclass
class OutputTemplate:
    """Representation of an output .py file.

    Each output file corresponds to a .proto input file,
    but may need references to other .proto files to be
    built.
    """

    parent_request: PluginRequestCompiler
    package_proto_obj: FileDescriptorProto
    input_files: List[str] = field(default_factory=list)
    imports_end: Set[str] = field(default_factory=set)
    datetime_imports: Set[str] = field(default_factory=set)
    pydantic_imports: Set[str] = field(default_factory=set)
    builtins_import: bool = False
    messages: List["MessageCompiler"] = field(default_factory=list)
    enums: List["EnumDefinitionCompiler"] = field(default_factory=list)
    services: List["ServiceCompiler"] = field(default_factory=list)
    imports_type_checking_only: Set[str] = field(default_factory=set)
    pydantic_dataclasses: bool = False
    output: bool = True
    typing_compiler: TypingCompiler = field(default_factory=DirectImportTypingCompiler)

    @property
    def package(self) -> str:
        """Name of input package.

        Returns
        -------
        str
            Name of input package.
        """
        return self.package_proto_obj.package

    @property
    def input_filenames(self) -> Iterable[str]:
        """Names of the input files used to build this output.

        Returns
        -------
        Iterable[str]
            Names of the input files used to build this output.
        """
        return sorted(f.name for f in self.input_files)

    @property
    def python_module_imports(self) -> Set[str]:
        imports = set()

        has_deprecated = False
        if any(m.deprecated for m in self.messages):
            has_deprecated = True
        if any(x for x in self.messages if any(x.deprecated_fields)):
            has_deprecated = True
        if any(
            any(m.proto_obj.options.deprecated for m in s.methods)
            for s in self.services
        ):
            has_deprecated = True

        if has_deprecated:
            imports.add("warnings")

        if self.builtins_import:
            imports.add("builtins")
        return imports


@dataclass
class MessageCompiler(ProtoContentBase):
    """Representation of a protobuf message."""

    source_file: FileDescriptorProto
    typing_compiler: TypingCompiler
    parent: Union["MessageCompiler", OutputTemplate] = PLACEHOLDER
    proto_obj: DescriptorProto = PLACEHOLDER
    path: List[int] = PLACEHOLDER
    fields: List[Union["FieldCompiler", "MessageCompiler"]] = field(
        default_factory=list
    )
    deprecated: bool = field(default=False, init=False)
    builtins_types: Set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        # Add message to output file
        if isinstance(self.parent, OutputTemplate):
            if isinstance(self, EnumDefinitionCompiler):
                self.output_file.enums.append(self)
            else:
                self.output_file.messages.append(self)
        self.deprecated = self.proto_obj.options.deprecated
        super().__post_init__()

    @property
    def proto_name(self) -> str:
        return self.proto_obj.name

    @property
    def py_name(self) -> str:
        return pythonize_class_name(self.proto_name)

    @property
    def deprecated_fields(self) -> Iterator[str]:
        for f in self.fields:
            if f.deprecated:
                yield f.py_name

    @property
    def has_deprecated_fields(self) -> bool:
        return any(self.deprecated_fields)

    @property
    def has_oneof_fields(self) -> bool:
        return any(isinstance(field, OneOfFieldCompiler) for field in self.fields)

    @property
    def has_message_field(self) -> bool:
        return any(
            (
                field.proto_obj.type in PROTO_MESSAGE_TYPES
                for field in self.fields
                if isinstance(field.proto_obj, FieldDescriptorProto)
            )
        )


def is_map(
    proto_field_obj: FieldDescriptorProto, parent_message: DescriptorProto
) -> bool:
    """True if proto_field_obj is a map, otherwise False."""
    if proto_field_obj.type == FieldDescriptorProtoType.TYPE_MESSAGE:
        if not hasattr(parent_message, "nested_type"):
            return False

        # This might be a map...
        message_type = proto_field_obj.type_name.split(".").pop().lower()
        map_entry = f"{proto_field_obj.name.replace('_', '').lower()}entry"
        if message_type == map_entry:
            for nested in parent_message.nested_type:  # parent message
                if (
                    nested.name.replace("_", "").lower() == map_entry
                    and nested.options.map_entry
                ):
                    return True
    return False


def is_oneof(proto_field_obj: FieldDescriptorProto) -> bool:
    """
    True if proto_field_obj is a OneOf, otherwise False.

    .. warning::
        Becuase the message from protoc is defined in proto2, and aristaproto works with
        proto3, and interpreting the FieldDescriptorProto.oneof_index field requires
        distinguishing between default and unset values (which proto3 doesn't support),
        we have to hack the generated FieldDescriptorProto class for this to work.
        The hack consists of setting group="oneof_index" in the field metadata,
        essentially making oneof_index the sole member of a one_of group, which allows
        us to tell whether it was set, via the which_one_of interface.
    """

    return (
        not proto_field_obj.proto3_optional
        and which_one_of(proto_field_obj, "oneof_index")[0] == "oneof_index"
    )


@dataclass
class FieldCompiler(MessageCompiler):
    parent: MessageCompiler = PLACEHOLDER
    proto_obj: FieldDescriptorProto = PLACEHOLDER

    def __post_init__(self) -> None:
        # Add field to message
        self.parent.fields.append(self)
        # Check for new imports
        self.add_imports_to(self.output_file)
        super().__post_init__()  # call FieldCompiler-> MessageCompiler __post_init__

    def get_field_string(self, indent: int = 4) -> str:
        """Construct string representation of this field as a field."""
        name = f"{self.py_name}"
        annotations = f": {self.annotation}"
        field_args = ", ".join(
            ([""] + self.aristaproto_field_args) if self.aristaproto_field_args else []
        )
        aristaproto_field_type = (
            f"aristaproto.{self.field_type}_field({self.proto_obj.number}{field_args})"
        )
        if self.py_name in dir(builtins):
            self.parent.builtins_types.add(self.py_name)
        return f"{name}{annotations} = {aristaproto_field_type}"

    @property
    def aristaproto_field_args(self) -> List[str]:
        args = []
        if self.field_wraps:
            args.append(f"wraps={self.field_wraps}")
        if self.optional:
            args.append("optional=True")
        return args

    @property
    def datetime_imports(self) -> Set[str]:
        imports = set()
        annotation = self.annotation
        # FIXME: false positives - e.g. `MyDatetimedelta`
        if "timedelta" in annotation:
            imports.add("timedelta")
        if "datetime" in annotation:
            imports.add("datetime")
        return imports

    @property
    def pydantic_imports(self) -> Set[str]:
        return set()

    @property
    def use_builtins(self) -> bool:
        return self.py_type in self.parent.builtins_types or (
            self.py_type == self.py_name and self.py_name in dir(builtins)
        )

    def add_imports_to(self, output_file: OutputTemplate) -> None:
        output_file.datetime_imports.update(self.datetime_imports)
        output_file.pydantic_imports.update(self.pydantic_imports)
        output_file.builtins_import = output_file.builtins_import or self.use_builtins

    @property
    def field_wraps(self) -> Optional[str]:
        """Returns aristaproto wrapped field type or None."""
        match_wrapper = re.match(
            r"\.google\.protobuf\.(.+)Value$", self.proto_obj.type_name
        )
        if match_wrapper:
            wrapped_type = "TYPE_" + match_wrapper.group(1).upper()
            if hasattr(aristaproto, wrapped_type):
                return f"aristaproto.{wrapped_type}"
        return None

    @property
    def repeated(self) -> bool:
        return (
            self.proto_obj.label == FieldDescriptorProtoLabel.LABEL_REPEATED
            and not is_map(self.proto_obj, self.parent)
        )

    @property
    def optional(self) -> bool:
        return self.proto_obj.proto3_optional

    @property
    def field_type(self) -> str:
        """String representation of proto field type."""
        return (
            FieldDescriptorProtoType(self.proto_obj.type)
            .name.lower()
            .replace("type_", "")
        )

    @property
    def packed(self) -> bool:
        """True if the wire representation is a packed format."""
        return self.repeated and self.proto_obj.type in PROTO_PACKED_TYPES

    @property
    def py_name(self) -> str:
        """Pythonized name."""
        return pythonize_field_name(self.proto_name)

    @property
    def proto_name(self) -> str:
        """Original protobuf name."""
        return self.proto_obj.name

    @property
    def py_type(self) -> str:
        """String representation of Python type."""
        if self.proto_obj.type in PROTO_FLOAT_TYPES:
            return "float"
        elif self.proto_obj.type in PROTO_INT_TYPES:
            return "int"
        elif self.proto_obj.type in PROTO_BOOL_TYPES:
            return "bool"
        elif self.proto_obj.type in PROTO_STR_TYPES:
            return "str"
        elif self.proto_obj.type in PROTO_BYTES_TYPES:
            return "bytes"
        elif self.proto_obj.type in PROTO_MESSAGE_TYPES:
            # Type referencing another defined Message or a named enum
            return get_type_reference(
                package=self.output_file.package,
                imports=self.output_file.imports_end,
                source_type=self.proto_obj.type_name,
                typing_compiler=self.typing_compiler,
                pydantic=self.output_file.pydantic_dataclasses,
            )
        else:
            raise NotImplementedError(f"Unknown type {self.proto_obj.type}")

    @property
    def annotation(self) -> str:
        py_type = self.py_type
        if self.use_builtins:
            py_type = f"builtins.{py_type}"
        if self.repeated:
            return self.typing_compiler.list(py_type)
        if self.optional:
            return self.typing_compiler.optional(py_type)
        return py_type


@dataclass
class OneOfFieldCompiler(FieldCompiler):
    @property
    def aristaproto_field_args(self) -> List[str]:
        args = super().aristaproto_field_args
        group = self.parent.proto_obj.oneof_decl[self.proto_obj.oneof_index].name
        args.append(f'group="{group}"')
        return args


@dataclass
class PydanticOneOfFieldCompiler(OneOfFieldCompiler):
    @property
    def optional(self) -> bool:
        # Force the optional to be True. This will allow the pydantic dataclass
        # to validate the object correctly by allowing the field to be let empty.
        # We add a pydantic validator later to ensure exactly one field is defined.
        return True

    @property
    def pydantic_imports(self) -> Set[str]:
        return {"model_validator"}


@dataclass
class MapEntryCompiler(FieldCompiler):
    py_k_type: Type = PLACEHOLDER
    py_v_type: Type = PLACEHOLDER
    proto_k_type: str = PLACEHOLDER
    proto_v_type: str = PLACEHOLDER

    def __post_init__(self) -> None:
        """Explore nested types and set k_type and v_type if unset."""
        map_entry = f"{self.proto_obj.name.replace('_', '').lower()}entry"
        for nested in self.parent.proto_obj.nested_type:
            if (
                nested.name.replace("_", "").lower() == map_entry
                and nested.options.map_entry
            ):
                # Get Python types
                self.py_k_type = FieldCompiler(
                    source_file=self.source_file,
                    parent=self,
                    proto_obj=nested.field[0],  # key
                    typing_compiler=self.typing_compiler,
                ).py_type
                self.py_v_type = FieldCompiler(
                    source_file=self.source_file,
                    parent=self,
                    proto_obj=nested.field[1],  # value
                    typing_compiler=self.typing_compiler,
                ).py_type

                # Get proto types
                self.proto_k_type = FieldDescriptorProtoType(nested.field[0].type).name
                self.proto_v_type = FieldDescriptorProtoType(nested.field[1].type).name
        super().__post_init__()  # call FieldCompiler-> MessageCompiler __post_init__

    @property
    def aristaproto_field_args(self) -> List[str]:
        return [f"aristaproto.{self.proto_k_type}", f"aristaproto.{self.proto_v_type}"]

    @property
    def field_type(self) -> str:
        return "map"

    @property
    def annotation(self) -> str:
        return self.typing_compiler.dict(self.py_k_type, self.py_v_type)

    @property
    def repeated(self) -> bool:
        return False  # maps cannot be repeated


@dataclass
class EnumDefinitionCompiler(MessageCompiler):
    """Representation of a proto Enum definition."""

    proto_obj: EnumDescriptorProto = PLACEHOLDER
    entries: List["EnumDefinitionCompiler.EnumEntry"] = PLACEHOLDER

    @dataclass(unsafe_hash=True)
    class EnumEntry:
        """Representation of an Enum entry."""

        name: str
        value: int
        comment: str

    def __post_init__(self) -> None:
        # Get entries/allowed values for this Enum
        self.entries = [
            self.EnumEntry(
                name=pythonize_enum_member_name(
                    entry_proto_value.name, self.proto_obj.name
                ),
                value=entry_proto_value.number,
                comment=get_comment(
                    proto_file=self.source_file, path=self.path + [2, entry_number]
                ),
            )
            for entry_number, entry_proto_value in enumerate(self.proto_obj.value)
        ]
        super().__post_init__()  # call MessageCompiler __post_init__


@dataclass
class ServiceCompiler(ProtoContentBase):
    source_file: FileDescriptorProto
    parent: OutputTemplate = PLACEHOLDER
    proto_obj: DescriptorProto = PLACEHOLDER
    path: List[int] = PLACEHOLDER
    methods: List["ServiceMethodCompiler"] = field(default_factory=list)

    def __post_init__(self) -> None:
        # Add service to output file
        self.output_file.services.append(self)
        super().__post_init__()  # check for unset fields

    @property
    def proto_name(self) -> str:
        return self.proto_obj.name

    @property
    def py_name(self) -> str:
        return pythonize_class_name(self.proto_name)


@dataclass
class ServiceMethodCompiler(ProtoContentBase):
    source_file: FileDescriptorProto
    parent: ServiceCompiler
    proto_obj: MethodDescriptorProto
    path: List[int] = PLACEHOLDER
    comment_indent: int = 8

    def __post_init__(self) -> None:
        # Add method to service
        self.parent.methods.append(self)

        self.output_file.imports_type_checking_only.add("import grpclib.server")
        self.output_file.imports_type_checking_only.add(
            "from aristaproto.grpc.grpclib_client import MetadataLike"
        )
        self.output_file.imports_type_checking_only.add(
            "from grpclib.metadata import Deadline"
        )

        super().__post_init__()  # check for unset fields

    @property
    def py_name(self) -> str:
        """Pythonized method name."""
        return pythonize_method_name(self.proto_obj.name)

    @property
    def proto_name(self) -> str:
        """Original protobuf name."""
        return self.proto_obj.name

    @property
    def route(self) -> str:
        package_part = (
            f"{self.output_file.package}." if self.output_file.package else ""
        )
        return f"/{package_part}{self.parent.proto_name}/{self.proto_name}"

    @property
    def py_input_message_type(self) -> str:
        """String representation of the Python type corresponding to the
        input message.

        Returns
        -------
        str
            String representation of the Python type corresponding to the input message.
        """
        return get_type_reference(
            package=self.output_file.package,
            imports=self.output_file.imports_end,
            source_type=self.proto_obj.input_type,
            typing_compiler=self.output_file.typing_compiler,
            unwrap=False,
            pydantic=self.output_file.pydantic_dataclasses,
        ).strip('"')

    @property
    def py_input_message_param(self) -> str:
        """Param name corresponding to py_input_message_type.

        Returns
        -------
        str
            Param name corresponding to py_input_message_type.
        """
        return pythonize_field_name(self.py_input_message_type)

    @property
    def py_output_message_type(self) -> str:
        """String representation of the Python type corresponding to the
        output message.

        Returns
        -------
        str
            String representation of the Python type corresponding to the output message.
        """
        return get_type_reference(
            package=self.output_file.package,
            imports=self.output_file.imports_end,
            source_type=self.proto_obj.output_type,
            typing_compiler=self.output_file.typing_compiler,
            unwrap=False,
            pydantic=self.output_file.pydantic_dataclasses,
        ).strip('"')

    @property
    def client_streaming(self) -> bool:
        return self.proto_obj.client_streaming

    @property
    def server_streaming(self) -> bool:
        return self.proto_obj.server_streaming
