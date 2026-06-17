from __future__ import annotations

import asyncio
import importlib
from collections.abc import AsyncIterable, AsyncIterator, Iterable
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any, Protocol

import pytest

if TYPE_CHECKING:
    import grpc

    class DoThingRequest(Protocol):
        name: str

    class DoThingResponse(Protocol):
        names: list[str]

    class GetThingRequest(Protocol):
        name: str

    class GetThingResponse(Protocol):
        name: str
        version: int


SERVICE_OUTPUT = "tests.outputs.service_client_async_transport_grpcio_server_async_transport_grpcio.service"


def service_output():
    return importlib.import_module(SERVICE_OUTPUT)


class GrpcioTestStub:
    def __init__(self, channel: grpc.aio.Channel, **kwargs: Any) -> None:
        from aristaproto.grpcio import ServiceStub

        self._stub = ServiceStub(channel, **kwargs)

    async def do_thing(self, message: DoThingRequest, **kwargs: Any) -> DoThingResponse:
        do_thing_response_type = service_output().DoThingResponse

        return await self._stub._unary_unary(
            "/service.Test/DoThing",
            message,
            do_thing_response_type,
            **kwargs,
        )

    async def do_many_things(
        self,
        messages: AsyncIterable[DoThingRequest] | Iterable[DoThingRequest],
        **kwargs: Any,
    ) -> DoThingResponse:
        output = service_output()
        do_thing_request_type = output.DoThingRequest
        do_thing_response_type = output.DoThingResponse

        return await self._stub._stream_unary(
            "/service.Test/DoManyThings",
            messages,
            do_thing_request_type,
            do_thing_response_type,
            **kwargs,
        )

    async def get_thing_versions(
        self,
        message: GetThingRequest,
        **kwargs: Any,
    ) -> AsyncIterator[GetThingResponse]:
        get_thing_response_type = service_output().GetThingResponse

        async for response in self._stub._unary_stream(
            "/service.Test/GetThingVersions",
            message,
            get_thing_response_type,
            **kwargs,
        ):
            yield response

    async def get_different_things(
        self,
        messages: AsyncIterable[GetThingRequest] | Iterable[GetThingRequest],
        **kwargs: Any,
    ) -> AsyncIterator[GetThingResponse]:
        output = service_output()
        get_thing_request_type = output.GetThingRequest
        get_thing_response_type = output.GetThingResponse

        async for response in self._stub._stream_stream(
            "/service.Test/GetDifferentThings",
            messages,
            get_thing_request_type,
            get_thing_response_type,
            **kwargs,
        ):
            yield response


@asynccontextmanager
async def grpcio_channel_for_handler(handler: Any) -> AsyncIterator[grpc.aio.Channel]:
    import grpc

    server = grpc.aio.server()
    server.add_generic_rpc_handlers((handler,))
    port = server.add_insecure_port("127.0.0.1:0")
    await server.start()

    channel = grpc.aio.insecure_channel(f"127.0.0.1:{port}")
    try:
        await channel.channel_ready()
        yield channel
    finally:
        await channel.close()
        await server.stop(0)


@asynccontextmanager
async def grpcio_channel_for_service(service: Any) -> AsyncIterator[grpc.aio.Channel]:
    async with grpcio_channel_for_handler(service._grpcio_rpc_handler()) as channel:
        yield channel


def grpcio_test_handler(
    *,
    do_thing=None,
    do_many_things=None,
    get_thing_versions=None,
    get_different_things=None,
):
    import grpc

    output = service_output()
    do_thing_request_type = output.DoThingRequest
    do_thing_response_type = output.DoThingResponse
    get_thing_request_type = output.GetThingRequest
    get_thing_response_type = output.GetThingResponse

    async def default_do_thing(request, context):  # NOSONAR: grpcio aio handlers are coroutine-shaped.
        return do_thing_response_type(names=[request.name])

    async def default_do_many_things(requests, context):
        return do_thing_response_type(names=[request.name async for request in requests])

    async def default_get_thing_versions(request, context):
        for version in range(1, 4):
            yield get_thing_response_type(name=request.name, version=version)

    async def default_get_different_things(requests, context):
        version = 0
        async for request in requests:
            version += 1
            yield get_thing_response_type(name=request.name, version=version)

    return grpc.method_handlers_generic_handler(
        "service.Test",
        {
            "DoThing": grpc.unary_unary_rpc_method_handler(
                do_thing or default_do_thing,
                request_deserializer=do_thing_request_type.FromString,
                response_serializer=do_thing_response_type.SerializeToString,
            ),
            "DoManyThings": grpc.stream_unary_rpc_method_handler(
                do_many_things or default_do_many_things,
                request_deserializer=do_thing_request_type.FromString,
                response_serializer=do_thing_response_type.SerializeToString,
            ),
            "GetThingVersions": grpc.unary_stream_rpc_method_handler(
                get_thing_versions or default_get_thing_versions,
                request_deserializer=get_thing_request_type.FromString,
                response_serializer=get_thing_response_type.SerializeToString,
            ),
            "GetDifferentThings": grpc.stream_stream_rpc_method_handler(
                get_different_things or default_get_different_things,
                request_deserializer=get_thing_request_type.FromString,
                response_serializer=get_thing_response_type.SerializeToString,
            ),
        },
    )


async def async_requests(names: Iterable[str]) -> AsyncIterator[DoThingRequest]:
    do_thing_request_type = service_output().DoThingRequest

    for name in names:
        yield do_thing_request_type(name=name)


def close_tracked_get_thing_requests() -> tuple[AsyncIterator[GetThingRequest], asyncio.Event, list[str]]:
    get_thing_request_type = service_output().GetThingRequest
    return _close_tracked_requests(get_thing_request_type)


def close_tracked_do_thing_requests() -> tuple[AsyncIterator[DoThingRequest], asyncio.Event, list[str]]:
    do_thing_request_type = service_output().DoThingRequest
    return _close_tracked_requests(do_thing_request_type)


def _close_tracked_requests(request_type: Any) -> tuple[AsyncIterator[Any], asyncio.Event, list[str]]:
    producer_closed = asyncio.Event()
    produced_names: list[str] = []

    async def requests():
        try:
            index = 0
            while True:
                index += 1
                name = f"request-{index}"
                produced_names.append(name)
                yield request_type(name=name)
                await asyncio.sleep(0.01)
        finally:
            producer_closed.set()

    return requests(), producer_closed, produced_names


async def assert_producer_closed(producer_closed: asyncio.Event, produced_names: list[str]) -> None:
    try:
        await asyncio.wait_for(producer_closed.wait(), timeout=1)
    except TimeoutError:
        pytest.fail(
            "request iterator was not closed after the RPC failed; "
            f"produced {len(produced_names)} request(s): {produced_names}",
        )


async def close_tracked_get_thing_responses(
    name: str,
    response_iterator_closed: asyncio.Event,
) -> AsyncIterator[GetThingResponse]:
    get_thing_response_type = service_output().GetThingResponse

    try:
        yield get_thing_response_type(name=name, version=1)
        await asyncio.sleep(10)
    finally:
        response_iterator_closed.set()


async def assert_response_iterator_closed(response_iterator_closed: asyncio.Event) -> None:
    await asyncio.wait_for(response_iterator_closed.wait(), timeout=1)


def unary_stream_response_cleanup_service(grpcio_test_base, response_iterator_closed: asyncio.Event):
    class UnaryStreamResponseCleanupService(grpcio_test_base):
        async def get_thing_versions(self, message):
            async for response in close_tracked_get_thing_responses(message.name, response_iterator_closed):
                yield response

    return UnaryStreamResponseCleanupService()


def stream_stream_response_cleanup_service(grpcio_test_base, response_iterator_closed: asyncio.Event):
    class StreamStreamResponseCleanupService(grpcio_test_base):
        async def get_different_things(self, messages):
            first_message = await anext(messages)
            async for response in close_tracked_get_thing_responses(first_message.name, response_iterator_closed):
                yield response

    return StreamStreamResponseCleanupService()


def make_generated_style_base():
    from aristaproto.grpcio import ServiceBase

    output = service_output()
    do_thing_request_type = output.DoThingRequest
    do_thing_response_type = output.DoThingResponse
    get_thing_request_type = output.GetThingRequest
    get_thing_response_type = output.GetThingResponse

    class TestBase(ServiceBase):
        async def do_thing(self, message: do_thing_request_type) -> do_thing_response_type:
            await self._grpcio_unimplemented()

        async def do_many_things(self, messages: AsyncIterator[do_thing_request_type]) -> do_thing_response_type:
            await self._grpcio_unimplemented()

        async def get_thing_versions(self, message: get_thing_request_type) -> AsyncIterator[get_thing_response_type]:
            await self._grpcio_unimplemented()
            yield get_thing_response_type()

        async def get_different_things(
            self,
            messages: AsyncIterator[get_thing_request_type],
        ) -> AsyncIterator[get_thing_response_type]:
            await self._grpcio_unimplemented()
            yield get_thing_response_type()

        def _grpcio_rpc_handler(self):
            return self._grpcio_generic_rpc_handler(
                "service.Test",
                {
                    "DoThing": self._grpcio_unary_unary_rpc_method_handler(
                        self.do_thing,
                        do_thing_request_type,
                        do_thing_response_type,
                    ),
                    "DoManyThings": self._grpcio_stream_unary_rpc_method_handler(
                        self.do_many_things,
                        do_thing_request_type,
                        do_thing_response_type,
                    ),
                    "GetThingVersions": self._grpcio_unary_stream_rpc_method_handler(
                        self.get_thing_versions,
                        get_thing_request_type,
                        get_thing_response_type,
                    ),
                    "GetDifferentThings": self._grpcio_stream_stream_rpc_method_handler(
                        self.get_different_things,
                        get_thing_request_type,
                        get_thing_response_type,
                    ),
                },
            )

    return TestBase
