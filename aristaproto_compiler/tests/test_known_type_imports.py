from collections.abc import Iterable
from pathlib import Path

from aristaproto_compiler.lib.google.protobuf import (
    DescriptorProto,
    FieldDescriptorProto,
    FieldDescriptorProtoLabel,
    FieldDescriptorProtoType,
    FileDescriptorProto,
    SourceCodeInfo,
)
from aristaproto_compiler.lib.google.protobuf.compiler import CodeGeneratorRequest
from aristaproto_compiler.plugin.parser import generate_code


def compile_message(package: str, message_name: str, fields: Iterable[FieldDescriptorProto]) -> str:
    source_file = FileDescriptorProto(
        name=f"{message_name.lower()}.proto",
        package=package,
        syntax="proto3",
        source_code_info=SourceCodeInfo(),
        message_type=[
            DescriptorProto(
                name=message_name,
                field=list(fields),
            ),
        ],
    )
    response = generate_code(
        CodeGeneratorRequest(
            file_to_generate=[source_file.name],
            proto_file=[source_file],
        )
    )

    output_file_name = Path(*package.split("."), "__init__.py")
    generated_files = {Path(file.name): file.content for file in response.file}

    return generated_files[output_file_name]


def test_timestamp_output_imports_nano_datetime() -> None:
    generated = compile_message(
        "google.protobuf",
        "Timestamp",
        [
            FieldDescriptorProto(
                name="seconds",
                number=1,
                label=FieldDescriptorProtoLabel.OPTIONAL,
                type=FieldDescriptorProtoType.INT64,
            ),
            FieldDescriptorProto(
                name="nanos",
                number=2,
                label=FieldDescriptorProtoLabel.OPTIONAL,
                type=FieldDescriptorProtoType.INT32,
            ),
        ],
    )

    assert "from aristaproto.nano_datetime import NanoDatetime" in generated
    assert "NanoDatetime.from_timestamp" in generated
    assert "dateutil.parser" not in generated


def test_non_timestamp_output_does_not_import_nano_datetime() -> None:
    generated = compile_message(
        "import_fixture",
        "NonTimestamp",
        [
            FieldDescriptorProto(
                name="value",
                number=1,
                label=FieldDescriptorProtoLabel.OPTIONAL,
                type=FieldDescriptorProtoType.BOOL,
            )
        ],
    )

    assert "aristaproto.nano_datetime" not in generated
