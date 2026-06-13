import ast
import asyncio
from pathlib import Path

import pytest

from tests.util import protoc

INPUTS = Path(__file__).parent / "inputs"


def generate_output(output_root: Path, fixture_name: str, output_name: str, **options: str) -> None:
    output_dir = output_root / output_name
    output_dir.mkdir()
    stdout, stderr, returncode = asyncio.run(protoc(INPUTS / fixture_name, output_dir, **options))
    assert returncode == 0, (stdout.decode(), stderr.decode())


@pytest.fixture(scope="module")
def generated_outputs(tmp_path_factory: pytest.TempPathFactory) -> Path:
    output_root = tmp_path_factory.mktemp("grpcio_generated_outputs")
    generate_output(output_root, "service", "service")
    generate_output(
        output_root,
        "service",
        "service_client_async_transport_grpcio",
        client_generation="async",
        server_generation="none",
        client_async_transport="grpcio",
    )
    generate_output(
        output_root,
        "service",
        "service_server_async_transport_grpcio",
        client_generation="none",
        server_generation="async",
        server_async_transport="grpcio",
    )
    generate_output(
        output_root,
        "service",
        "service_client_async_transport_grpcio_server_async_transport_grpcio",
        client_generation="async",
        server_generation="async",
        client_async_transport="grpcio",
        server_async_transport="grpcio",
    )
    generate_output(
        output_root,
        "documentation",
        "documentation_client_async_transport_grpcio_server_async_transport_grpcio",
        client_generation="async",
        server_generation="async",
        client_async_transport="grpcio",
        server_async_transport="grpcio",
    )
    return output_root


def read_output(output_root: Path, *parts: str) -> str:
    return (output_root.joinpath(*parts) / "__init__.py").read_text()


def get_all(source: str) -> tuple[str, ...]:
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "__all__":
                    return ast.literal_eval(node.value)
    raise AssertionError("__all__ assignment not found")


def test_grpcio_async_client_generated_shape(generated_outputs: Path) -> None:
    source = read_output(generated_outputs, "service_client_async_transport_grpcio", "service")

    assert "from aristaproto import grpcio as aristaproto_grpcio" in source
    assert "from aristaproto import grpclib as aristaproto_grpclib" not in source
    assert "class TestStub(aristaproto_grpcio.ServiceStub):" in source

    assert 'timeout: "float | None" = None' in source
    assert 'metadata: "MetadataLike | None" = None' in source
    assert 'credentials: "grpc.CallCredentials | None" = None' in source
    assert 'wait_for_ready: "bool | None" = None' in source
    assert "deadline" not in source


def test_grpcio_async_server_generated_shape(generated_outputs: Path) -> None:
    source = read_output(generated_outputs, "service_server_async_transport_grpcio", "service")

    assert "from aristaproto import grpcio as aristaproto_grpcio" in source
    assert "from aristaproto import grpclib as aristaproto_grpclib" not in source
    assert "class TestBase(aristaproto_grpcio.ServiceBase):" in source
    assert "def _grpcio_rpc_handler(self) -> grpc.GenericRpcHandler:" in source
    assert "__mapping__" not in source


def test_default_async_generation_remains_grpclib_shaped(generated_outputs: Path) -> None:
    source = read_output(generated_outputs, "service", "service")

    assert "from aristaproto import grpclib as aristaproto_grpclib" in source
    assert "from aristaproto import grpcio as aristaproto_grpcio" not in source
    assert "class TestStub(aristaproto_grpclib.ServiceStub):" in source
    assert "class TestBase(aristaproto_grpclib.ServiceBase):" in source
    assert "deadline" in source
    assert "def __mapping__(self)" in source
    assert "_grpcio_rpc_handler" not in source


def test_grpcio_async_all_exports_include_messages_enum_stub_and_base(generated_outputs: Path) -> None:
    source = read_output(
        generated_outputs,
        "service_client_async_transport_grpcio_server_async_transport_grpcio",
        "service",
    )

    assert get_all(source) == (
        "DoThingRequest",
        "DoThingResponse",
        "GetThingRequest",
        "GetThingResponse",
        "TestBase",
        "TestStub",
        "ThingType",
    )


def test_default_all_exports_still_include_sync_stub(generated_outputs: Path) -> None:
    source = read_output(generated_outputs, "service", "service")

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


def test_documentation_comments_are_preserved_on_grpcio_async_stub_and_base(generated_outputs: Path) -> None:
    source = read_output(
        generated_outputs,
        "documentation_client_async_transport_grpcio_server_async_transport_grpcio",
        "documentation",
    )

    assert "class ServiceStub(aristaproto_grpcio.ServiceStub):" in source
    assert "class ServiceBase(aristaproto_grpcio.ServiceBase):" in source
    assert "Documentation of service 1" in source
    assert "Documentation of service 2" in source
    assert "Documentation of service 3" in source
    assert "Documentation of method 1" in source
    assert "Documentation of method 2" in source
    assert "Documentation of method 3" in source
