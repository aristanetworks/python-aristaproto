from __future__ import annotations

import asyncio
from typing import (
    AsyncIterator,
)

import grpc
import pytest
import pytest_asyncio

from aristaproto.grpcio_server import ServiceBase
from tests.grpcio.service_fixtures import (
    DO_THING_ROUTE,
    GeneratedStyleTestStub,
    async_do_thing_requests,
    async_get_thing_requests,
    collect_get_thing_responses,
)
from tests.output_aristaproto.service import (
    DoThingRequest,
    DoThingResponse,
    GetThingRequest,
    GetThingResponse,
)


class HandwrittenGeneratedTestBase(ServiceBase):
    async def do_thing(self, do_thing_request: DoThingRequest) -> DoThingResponse:
        return await self._grpcio_unimplemented("service.Test.DoThing")

    async def do_many_things(
        self,
        do_thing_request_iterator: AsyncIterator[DoThingRequest],
    ) -> DoThingResponse:
        return await self._grpcio_unimplemented("service.Test.DoManyThings")

    async def get_thing_versions(
        self,
        get_thing_request: GetThingRequest,
    ) -> AsyncIterator[GetThingResponse]:
        await self._grpcio_unimplemented("service.Test.GetThingVersions")
        yield GetThingResponse()

    async def get_different_things(
        self,
        get_thing_request_iterator: AsyncIterator[GetThingRequest],
    ) -> AsyncIterator[GetThingResponse]:
        await self._grpcio_unimplemented("service.Test.GetDifferentThings")
        yield GetThingResponse()

    def _grpcio_rpc_handler(self) -> grpc.GenericRpcHandler:
        return self._grpcio_generic_rpc_handler(
            "service.Test",
            {
                "DoThing": self._grpcio_unary_unary_rpc_method_handler(
                    self.do_thing,
                    DoThingRequest,
                    DoThingResponse,
                ),
                "DoManyThings": self._grpcio_stream_unary_rpc_method_handler(
                    self.do_many_things,
                    DoThingRequest,
                    DoThingResponse,
                ),
                "GetThingVersions": self._grpcio_unary_stream_rpc_method_handler(
                    self.get_thing_versions,
                    GetThingRequest,
                    GetThingResponse,
                ),
                "GetDifferentThings": self._grpcio_stream_stream_rpc_method_handler(
                    self.get_different_things,
                    GetThingRequest,
                    GetThingResponse,
                ),
            },
        )


class RecordingGeneratedTestService(HandwrittenGeneratedTestBase):
    def __init__(self) -> None:
        self.metadata = ()
        self.metadata_by_name: dict[str, str] = {}

    async def do_thing(self, do_thing_request: DoThingRequest) -> DoThingResponse:
        self.metadata = self._grpcio_context.invocation_metadata()
        if do_thing_request.name.startswith("concurrent-"):
            await asyncio.sleep(0.01)
            self.metadata_by_name[do_thing_request.name] = dict(
                self._grpcio_context.invocation_metadata()
            )["authorization"]
        if do_thing_request.name == "invalid":
            await self._grpcio_context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                "invalid thing",
            )
        self._grpcio_context.set_trailing_metadata((("processed-by", "grpcio"),))
        return DoThingResponse(names=[do_thing_request.name])

    async def do_many_things(
        self,
        do_thing_request_iterator: AsyncIterator[DoThingRequest],
    ) -> DoThingResponse:
        return DoThingResponse(
            names=[
                do_thing_request.name
                async for do_thing_request in do_thing_request_iterator
            ]
        )

    async def get_thing_versions(
        self,
        get_thing_request: GetThingRequest,
    ) -> AsyncIterator[GetThingResponse]:
        for version in range(1, 4):
            yield GetThingResponse(name=get_thing_request.name, version=version)

    async def get_different_things(
        self,
        get_thing_request_iterator: AsyncIterator[GetThingRequest],
    ) -> AsyncIterator[GetThingResponse]:
        version = 0
        async for get_thing_request in get_thing_request_iterator:
            version += 1
            yield GetThingResponse(name=get_thing_request.name, version=version)


@pytest_asyncio.fixture
async def grpcio_service():
    service = RecordingGeneratedTestService()
    server = grpc.aio.server()
    server.add_generic_rpc_handlers((service._grpcio_rpc_handler(),))
    port = server.add_insecure_port("127.0.0.1:0")
    await server.start()
    channel = grpc.aio.insecure_channel(f"127.0.0.1:{port}")
    try:
        yield GeneratedStyleTestStub(channel), service
    finally:
        await channel.close()
        await server.stop(grace=None)


@pytest_asyncio.fixture
async def unimplemented_grpcio_service():
    service = HandwrittenGeneratedTestBase()
    server = grpc.aio.server()
    server.add_generic_rpc_handlers((service._grpcio_rpc_handler(),))
    port = server.add_insecure_port("127.0.0.1:0")
    await server.start()
    channel = grpc.aio.insecure_channel(f"127.0.0.1:{port}")
    try:
        yield GeneratedStyleTestStub(channel)
    finally:
        await channel.close()
        await server.stop(grace=None)


def metadata_value(service: RecordingGeneratedTestService, key: str) -> str:
    return dict(service.metadata)[key]


@pytest.mark.asyncio
async def test_unary_unary(grpcio_service):
    client, _service = grpcio_service

    response = await client.do_thing(DoThingRequest(name="clean room"))

    assert response == DoThingResponse(names=["clean room"])


@pytest.mark.asyncio
async def test_unary_stream(grpcio_service):
    client, _service = grpcio_service

    responses = await collect_get_thing_responses(
        client.get_thing_versions(GetThingRequest(name="switch"))
    )

    assert responses == [
        GetThingResponse(name="switch", version=1),
        GetThingResponse(name="switch", version=2),
        GetThingResponse(name="switch", version=3),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "request_iterator",
    [
        [DoThingRequest(name="one"), DoThingRequest(name="two")],
        async_do_thing_requests(["one", "two"]),
    ],
)
async def test_stream_unary(grpcio_service, request_iterator):
    client, _service = grpcio_service

    response = await client.do_many_things(request_iterator)

    assert response == DoThingResponse(names=["one", "two"])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "request_iterator",
    [
        [GetThingRequest(name="leaf"), GetThingRequest(name="spine")],
        async_get_thing_requests(["leaf", "spine"]),
    ],
)
async def test_stream_stream(grpcio_service, request_iterator):
    client, _service = grpcio_service

    responses = await collect_get_thing_responses(
        client.get_different_things(request_iterator)
    )

    assert responses == [
        GetThingResponse(name="leaf", version=1),
        GetThingResponse(name="spine", version=2),
    ]


@pytest.mark.asyncio
async def test_context_hook_provides_metadata(grpcio_service):
    client, service = grpcio_service

    await client.do_thing(
        DoThingRequest(name="metadata"),
        metadata={"authorization": "token"},
    )

    assert metadata_value(service, "authorization") == "token"


@pytest.mark.asyncio
async def test_context_hook_is_isolated_across_concurrent_rpcs(grpcio_service):
    client, service = grpcio_service

    await asyncio.gather(
        client.do_thing(
            DoThingRequest(name="concurrent-one"),
            metadata={"authorization": "token-one"},
        ),
        client.do_thing(
            DoThingRequest(name="concurrent-two"),
            metadata={"authorization": "token-two"},
        ),
    )

    assert service.metadata_by_name == {
        "concurrent-one": "token-one",
        "concurrent-two": "token-two",
    }


@pytest.mark.asyncio
async def test_context_hook_sets_trailing_metadata(grpcio_service):
    client, _service = grpcio_service
    call = client.channel.unary_unary(
        DO_THING_ROUTE,
        request_serializer=DoThingRequest.SerializeToString,
        response_deserializer=DoThingResponse.FromString,
    )

    response_call = call(DoThingRequest(name="metadata"))
    response = await response_call

    assert response == DoThingResponse(names=["metadata"])
    assert dict(await response_call.trailing_metadata())["processed-by"] == "grpcio"


@pytest.mark.asyncio
async def test_context_hook_sets_status(grpcio_service):
    client, _service = grpcio_service

    with pytest.raises(grpc.aio.AioRpcError) as error:
        await client.do_thing(DoThingRequest(name="invalid"))

    assert error.value.code() == grpc.StatusCode.INVALID_ARGUMENT
    assert error.value.details() == "invalid thing"


@pytest.mark.asyncio
async def test_unimplemented_base_methods_raise_grpcio_unimplemented(
    unimplemented_grpcio_service,
):
    client = unimplemented_grpcio_service

    with pytest.raises(grpc.aio.AioRpcError) as error:
        await client.do_thing(DoThingRequest(name="missing"))

    assert error.value.code() == grpc.StatusCode.UNIMPLEMENTED
