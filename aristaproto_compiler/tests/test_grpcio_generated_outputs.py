import ast
from pathlib import Path

OUTPUTS = Path(__file__).parent / "outputs"


def read_output(*parts: str) -> str:
    return (OUTPUTS.joinpath(*parts) / "__init__.py").read_text()


def get_all(source: str) -> tuple[str, ...]:
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "__all__":
                    return ast.literal_eval(node.value)
    raise AssertionError("__all__ assignment not found")


def test_grpcio_async_client_generated_shape() -> None:
    source = read_output("service_client_async_transport_grpcio", "service")

    assert "from aristaproto import grpcio as aristaproto_grpcio" in source
    assert "from aristaproto import grpclib as aristaproto_grpclib" not in source
    assert "class TestStub(aristaproto_grpcio.ServiceStub):" in source

    assert 'timeout: "float | None" = None' in source
    assert 'metadata: "MetadataLike | None" = None' in source
    assert 'credentials: "grpc.CallCredentials | None" = None' in source
    assert 'wait_for_ready: "bool | None" = None' in source
    assert "deadline" not in source


def test_grpcio_async_server_generated_shape() -> None:
    source = read_output("service_server_async_transport_grpcio", "service")

    assert "from aristaproto import grpcio as aristaproto_grpcio" in source
    assert "from aristaproto import grpclib as aristaproto_grpclib" not in source
    assert "class TestBase(aristaproto_grpcio.ServiceBase):" in source
    assert "def _grpcio_rpc_handler(self) -> grpc.GenericRpcHandler:" in source
    assert "__mapping__" not in source


def test_default_async_generation_remains_grpclib_shaped() -> None:
    source = read_output("service", "service")

    assert "from aristaproto import grpclib as aristaproto_grpclib" in source
    assert "from aristaproto import grpcio as aristaproto_grpcio" not in source
    assert "class TestStub(aristaproto_grpclib.ServiceStub):" in source
    assert "class TestBase(aristaproto_grpclib.ServiceBase):" in source
    assert "deadline" in source
    assert "def __mapping__(self)" in source
    assert "_grpcio_rpc_handler" not in source


def test_grpcio_async_all_exports_include_messages_enum_stub_and_base() -> None:
    source = read_output("service_client_async_transport_grpcio_server_async_transport_grpcio", "service")

    assert get_all(source) == (
        "DoThingRequest",
        "DoThingResponse",
        "GetThingRequest",
        "GetThingResponse",
        "TestBase",
        "TestStub",
        "ThingType",
    )


def test_default_all_exports_still_include_sync_stub() -> None:
    source = read_output("service", "service")

    assert get_all(source) == (
        "DoThingRequest",
        "DoThingResponse",
        "GetThingRequest",
        "GetThingResponse",
        "TestBase",
        "TestStub",
        "TestSyncStub",
        "ThingType",
    )


def test_documentation_comments_are_preserved_on_grpcio_async_stub_and_base() -> None:
    source = read_output("documentation_client_async_transport_grpcio_server_async_transport_grpcio", "documentation")

    assert "class ServiceStub(aristaproto_grpcio.ServiceStub):" in source
    assert "class ServiceBase(aristaproto_grpcio.ServiceBase):" in source
    assert "Documentation of service 1" in source
    assert "Documentation of service 2" in source
    assert "Documentation of service 3" in source
    assert "Documentation of method 1" in source
    assert "Documentation of method 2" in source
    assert "Documentation of method 3" in source
