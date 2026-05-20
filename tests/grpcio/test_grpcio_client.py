import asyncio
from typing import (
    AsyncIterable,
    AsyncIterator,
    Iterable,
    Optional,
    Union,
)

import grpc
import pytest
import pytest_asyncio

from aristaproto.grpcio_client import (
    MetadataLike,
    ServiceStub,
)
from tests.output_aristaproto.service import (
    DoThingRequest,
    DoThingResponse,
    GetThingRequest,
    GetThingResponse,
)


class HandwrittenGrpcioStub(ServiceStub):
    async def do_thing(
        self,
        do_thing_request: DoThingRequest,
        *,
        timeout: Optional[float] = None,
        metadata: Optional[MetadataLike] = None,
        credentials: Optional[grpc.CallCredentials] = None,
        wait_for_ready: Optional[bool] = None,
    ) -> DoThingResponse:
        return await self._unary_unary(
            "/service.Test/DoThing",
            do_thing_request,
            DoThingResponse,
            timeout=timeout,
            metadata=metadata,
            credentials=credentials,
            wait_for_ready=wait_for_ready,
        )

    async def do_many_things(
        self,
        do_thing_request_iterator: Union[
            AsyncIterable[DoThingRequest],
            Iterable[DoThingRequest],
        ],
        *,
        timeout: Optional[float] = None,
        metadata: Optional[MetadataLike] = None,
        credentials: Optional[grpc.CallCredentials] = None,
        wait_for_ready: Optional[bool] = None,
    ) -> DoThingResponse:
        return await self._stream_unary(
            "/service.Test/DoManyThings",
            do_thing_request_iterator,
            DoThingRequest,
            DoThingResponse,
            timeout=timeout,
            metadata=metadata,
            credentials=credentials,
            wait_for_ready=wait_for_ready,
        )

    async def get_thing_versions(
        self,
        get_thing_request: GetThingRequest,
        *,
        timeout: Optional[float] = None,
        metadata: Optional[MetadataLike] = None,
        credentials: Optional[grpc.CallCredentials] = None,
        wait_for_ready: Optional[bool] = None,
    ) -> AsyncIterator[GetThingResponse]:
        async for response in self._unary_stream(
            "/service.Test/GetThingVersions",
            get_thing_request,
            GetThingResponse,
            timeout=timeout,
            metadata=metadata,
            credentials=credentials,
            wait_for_ready=wait_for_ready,
        ):
            yield response

    async def get_different_things(
        self,
        get_thing_request_iterator: Union[
            AsyncIterable[GetThingRequest],
            Iterable[GetThingRequest],
        ],
        *,
        timeout: Optional[float] = None,
        metadata: Optional[MetadataLike] = None,
        credentials: Optional[grpc.CallCredentials] = None,
        wait_for_ready: Optional[bool] = None,
    ) -> AsyncIterator[GetThingResponse]:
        async for response in self._stream_stream(
            "/service.Test/GetDifferentThings",
            get_thing_request_iterator,
            GetThingRequest,
            GetThingResponse,
            timeout=timeout,
            metadata=metadata,
            credentials=credentials,
            wait_for_ready=wait_for_ready,
        ):
            yield response


class RecordingGrpcioService:
    def __init__(self) -> None:
        self.metadata = ()

    async def do_thing(
        self,
        request: DoThingRequest,
        context: grpc.aio.ServicerContext,
    ) -> DoThingResponse:
        self.metadata = context.invocation_metadata()
        if request.name == "slow":
            await asyncio.sleep(1)
        if request.name == "unauthenticated":
            await context.abort(grpc.StatusCode.UNAUTHENTICATED, "not allowed")
        return DoThingResponse(names=[request.name])

    async def do_many_things(
        self,
        request_iterator: AsyncIterator[DoThingRequest],
        context: grpc.aio.ServicerContext,
    ) -> DoThingResponse:
        self.metadata = context.invocation_metadata()
        return DoThingResponse(
            names=[request.name async for request in request_iterator]
        )

    async def get_thing_versions(
        self,
        request: GetThingRequest,
        context: grpc.aio.ServicerContext,
    ) -> AsyncIterator[GetThingResponse]:
        self.metadata = context.invocation_metadata()
        for version in range(1, 4):
            yield GetThingResponse(name=request.name, version=version)

    async def get_different_things(
        self,
        request_iterator: AsyncIterator[GetThingRequest],
        context: grpc.aio.ServicerContext,
    ) -> AsyncIterator[GetThingResponse]:
        self.metadata = context.invocation_metadata()
        version = 0
        async for request in request_iterator:
            version += 1
            yield GetThingResponse(name=request.name, version=version)

    def handler(self) -> grpc.GenericRpcHandler:
        return grpc.method_handlers_generic_handler(
            "service.Test",
            {
                "DoThing": grpc.unary_unary_rpc_method_handler(
                    self.do_thing,
                    request_deserializer=DoThingRequest.FromString,
                    response_serializer=DoThingResponse.SerializeToString,
                ),
                "DoManyThings": grpc.stream_unary_rpc_method_handler(
                    self.do_many_things,
                    request_deserializer=DoThingRequest.FromString,
                    response_serializer=DoThingResponse.SerializeToString,
                ),
                "GetThingVersions": grpc.unary_stream_rpc_method_handler(
                    self.get_thing_versions,
                    request_deserializer=GetThingRequest.FromString,
                    response_serializer=GetThingResponse.SerializeToString,
                ),
                "GetDifferentThings": grpc.stream_stream_rpc_method_handler(
                    self.get_different_things,
                    request_deserializer=GetThingRequest.FromString,
                    response_serializer=GetThingResponse.SerializeToString,
                ),
            },
        )


@pytest_asyncio.fixture
async def grpcio_service():
    service = RecordingGrpcioService()
    server = grpc.aio.server()
    server.add_generic_rpc_handlers((service.handler(),))
    port = server.add_insecure_port("127.0.0.1:0")
    await server.start()
    channel = grpc.aio.insecure_channel(f"127.0.0.1:{port}")
    try:
        yield HandwrittenGrpcioStub(channel), service
    finally:
        await channel.close()
        await server.stop(grace=None)


async def async_do_thing_requests(
    names: Iterable[str],
) -> AsyncIterator[DoThingRequest]:
    for name in names:
        yield DoThingRequest(name=name)


async def async_get_thing_requests(
    names: Iterable[str],
) -> AsyncIterator[GetThingRequest]:
    for name in names:
        yield GetThingRequest(name=name)


async def collect(iterator: AsyncIterator[GetThingResponse]):
    return [message async for message in iterator]


def metadata_value(service: RecordingGrpcioService, key: str) -> str:
    return dict(service.metadata)[key]


@pytest.mark.asyncio
async def test_unary_unary(grpcio_service):
    client, _service = grpcio_service

    response = await client.do_thing(DoThingRequest(name="clean room"))

    assert response == DoThingResponse(names=["clean room"])


@pytest.mark.asyncio
async def test_unary_stream(grpcio_service):
    client, _service = grpcio_service

    responses = await collect(client.get_thing_versions(GetThingRequest(name="switch")))

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
async def test_stream_unary_accepts_sync_and_async_iterables(
    grpcio_service,
    request_iterator,
):
    client, _service = grpcio_service

    response = await client.do_many_things(request_iterator)

    assert response == DoThingResponse(names=["one", "two"])


@pytest.mark.asyncio
async def test_stream_stream_accepts_sync_iterables(grpcio_service):
    client, _service = grpcio_service

    responses = await collect(
        client.get_different_things(
            [GetThingRequest(name="leaf"), GetThingRequest(name="spine")]
        )
    )

    assert responses == [
        GetThingResponse(name="leaf", version=1),
        GetThingResponse(name="spine", version=2),
    ]


@pytest.mark.asyncio
async def test_stream_stream_accepts_async_iterables(grpcio_service):
    client, _service = grpcio_service

    responses = await collect(
        client.get_different_things(async_get_thing_requests(["leaf", "spine"]))
    )

    assert responses == [
        GetThingResponse(name="leaf", version=1),
        GetThingResponse(name="spine", version=2),
    ]


@pytest.mark.asyncio
async def test_metadata_override_precedence(grpcio_service):
    client, service = grpcio_service
    client.metadata = {"authorization": "default"}

    await client.do_thing(
        DoThingRequest(name="metadata"),
        metadata={"authorization": "override"},
    )

    assert metadata_value(service, "authorization") == "override"


@pytest.mark.asyncio
async def test_timeout_override_precedence(grpcio_service):
    client, _service = grpcio_service
    client.timeout = 10

    with pytest.raises(grpc.aio.AioRpcError) as error:
        await client.do_thing(DoThingRequest(name="slow"), timeout=0.01)

    assert error.value.code() == grpc.StatusCode.DEADLINE_EXCEEDED


@pytest.mark.asyncio
async def test_grpcio_error_propagation(grpcio_service):
    client, _service = grpcio_service

    with pytest.raises(grpc.aio.AioRpcError) as error:
        await client.do_thing(DoThingRequest(name="unauthenticated"))

    assert error.value.code() == grpc.StatusCode.UNAUTHENTICATED
