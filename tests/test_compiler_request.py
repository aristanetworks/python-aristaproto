from aristaproto.lib.google.protobuf import FileDescriptorProto
from aristaproto.lib.google.protobuf.compiler import CodeGeneratorRequest


def test_compiler_request_round_trip():
    request = CodeGeneratorRequest(
        file_to_generate=["example.proto"],
        proto_file=[FileDescriptorProto(name="example.proto", package="example")],
    )

    assert CodeGeneratorRequest().parse(bytes(request)) == request
