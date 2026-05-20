import importlib
import inspect
import sys
from types import ModuleType
from typing import (
    AsyncIterator,
)

import grpc
import pytest
import pytest_asyncio

from aristaproto.grpcio_client import ServiceStub as GrpcioServiceStub
from aristaproto.grpcio_server import ServiceBase as GrpcioServiceBase
from tests.util import (
    inputs_path,
    protoc,
)


@pytest_asyncio.fixture
async def generated_service_module(tmp_path, reset_sys_path):
    stdout, stderr, returncode = await protoc(
        inputs_path.joinpath("service"),
        tmp_path,
        plugin_options=("transport=grpcio",),
    )

    assert returncode == 0, (
        f"protoc failed\nstdout:\n{stdout.decode()}\nstderr:\n{stderr.decode()}"
    )

    sys.path.insert(0, str(tmp_path))
    sys.modules.pop("service", None)
    try:
        yield (
            importlib.import_module("service"),
            tmp_path.joinpath("service", "__init__.py").read_text(),
        )
    finally:
        sys.modules.pop("service", None)


def test_generated_grpcio_code_shape(
    generated_service_module: tuple[ModuleType, str],
) -> None:
    module, source = generated_service_module

    assert "from aristaproto.grpcio_client import" in source
    assert "from aristaproto.grpcio_server import ServiceBase" in source
    assert "import grpc" in source
    assert "grpclib" not in source
    assert "class TestStub(ServiceStub):" in source
    assert "class TestBase(ServiceBase):" in source
    assert "def _grpcio_rpc_handler(self) -> grpc.GenericRpcHandler:" in source
    assert "__mapping__" not in source
    assert "deadline" not in inspect.signature(module.TestStub.do_thing).parameters
    assert set(inspect.signature(module.TestStub.do_thing).parameters) == {
        "self",
        "do_thing_request",
        "timeout",
        "metadata",
        "credentials",
        "wait_for_ready",
    }
    assert issubclass(module.TestStub, GrpcioServiceStub)
    assert issubclass(module.TestBase, GrpcioServiceBase)


async def async_get_thing_requests(
    module: ModuleType,
    names: list[str],
) -> AsyncIterator:
    for name in names:
        yield module.GetThingRequest(name=name)


@pytest_asyncio.fixture
async def generated_grpcio_service(generated_service_module):
    module, _source = generated_service_module

    class RecordingGeneratedService(module.TestBase):
        async def do_thing(self, do_thing_request):
            return module.DoThingResponse(names=[do_thing_request.name])

        async def do_many_things(self, do_thing_request_iterator):
            return module.DoThingResponse(
                names=[
                    do_thing_request.name
                    async for do_thing_request in do_thing_request_iterator
                ]
            )

        async def get_thing_versions(self, get_thing_request):
            for version in range(1, 4):
                yield module.GetThingResponse(
                    name=get_thing_request.name,
                    version=version,
                )

        async def get_different_things(self, get_thing_request_iterator):
            version = 0
            async for get_thing_request in get_thing_request_iterator:
                version += 1
                yield module.GetThingResponse(
                    name=get_thing_request.name,
                    version=version,
                )

    service = RecordingGeneratedService()
    server = grpc.aio.server()
    server.add_generic_rpc_handlers((service._grpcio_rpc_handler(),))
    port = server.add_insecure_port("127.0.0.1:0")
    await server.start()
    channel = grpc.aio.insecure_channel(f"127.0.0.1:{port}")
    try:
        yield module.TestStub(channel), module
    finally:
        await channel.close()
        await server.stop(grace=None)


@pytest.mark.asyncio
async def test_generated_grpcio_stubs_and_bases_support_all_cardinalities(
    generated_grpcio_service,
) -> None:
    client, module = generated_grpcio_service

    response = await client.do_thing(module.DoThingRequest(name="clean room"))
    assert response == module.DoThingResponse(names=["clean room"])

    unary_stream_responses = [
        response
        async for response in client.get_thing_versions(
            module.GetThingRequest(name="switch")
        )
    ]
    assert unary_stream_responses == [
        module.GetThingResponse(name="switch", version=1),
        module.GetThingResponse(name="switch", version=2),
        module.GetThingResponse(name="switch", version=3),
    ]

    stream_unary_response = await client.do_many_things(
        [
            module.DoThingRequest(name="one"),
            module.DoThingRequest(name="two"),
        ]
    )
    assert stream_unary_response == module.DoThingResponse(names=["one", "two"])

    stream_stream_responses = [
        response
        async for response in client.get_different_things(
            async_get_thing_requests(module, ["leaf", "spine"])
        )
    ]
    assert stream_stream_responses == [
        module.GetThingResponse(name="leaf", version=1),
        module.GetThingResponse(name="spine", version=2),
    ]


@pytest.mark.asyncio
async def test_generated_grpcio_base_unimplemented_methods_raise_grpcio_status(
    generated_service_module,
) -> None:
    module, _source = generated_service_module
    service = module.TestBase()
    server = grpc.aio.server()
    server.add_generic_rpc_handlers((service._grpcio_rpc_handler(),))
    port = server.add_insecure_port("127.0.0.1:0")
    await server.start()
    channel = grpc.aio.insecure_channel(f"127.0.0.1:{port}")
    try:
        client = module.TestStub(channel)
        with pytest.raises(grpc.aio.AioRpcError) as error:
            await client.do_thing(module.DoThingRequest(name="missing"))

        assert error.value.code() == grpc.StatusCode.UNIMPLEMENTED
    finally:
        await channel.close()
        await server.stop(grace=None)
