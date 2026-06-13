from __future__ import annotations

import asyncio
import importlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import pytest

SERVICE_OUTPUT = "tests.outputs.service_client_async_transport_grpcio_server_async_transport_grpcio.service"


def service_output():
    return importlib.import_module(SERVICE_OUTPUT)


class GrpcioTestStub:
    def __init__(self, channel, **kwargs):
        from aristaproto.grpcio import ServiceStub

        self._stub = ServiceStub(channel, **kwargs)

    async def do_thing(self, message, **kwargs) -> Any:
        DoThingResponse = service_output().DoThingResponse

        return await self._stub._unary_unary(
            "/service.Test/DoThing",
            message,
            DoThingResponse,
            **kwargs,
        )

    async def do_many_things(self, messages, **kwargs) -> Any:
        output = service_output()
        DoThingRequest = output.DoThingRequest
        DoThingResponse = output.DoThingResponse

        return await self._stub._stream_unary(
            "/service.Test/DoManyThings",
            messages,
            DoThingRequest,
            DoThingResponse,
            **kwargs,
        )

    async def get_thing_versions(self, message, **kwargs) -> AsyncIterator[Any]:
        GetThingResponse = service_output().GetThingResponse

        async for response in self._stub._unary_stream(
            "/service.Test/GetThingVersions",
            message,
            GetThingResponse,
            **kwargs,
        ):
            yield response

    async def get_different_things(self, messages, **kwargs) -> AsyncIterator[Any]:
        output = service_output()
        GetThingRequest = output.GetThingRequest
        GetThingResponse = output.GetThingResponse

        async for response in self._stub._stream_stream(
            "/service.Test/GetDifferentThings",
            messages,
            GetThingRequest,
            GetThingResponse,
            **kwargs,
        ):
            yield response


@asynccontextmanager
async def grpcio_channel_for_handler(handler) -> AsyncIterator:
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
async def grpcio_channel_for_service(service) -> AsyncIterator:
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
    DoThingRequest = output.DoThingRequest
    DoThingResponse = output.DoThingResponse
    GetThingRequest = output.GetThingRequest
    GetThingResponse = output.GetThingResponse

    async def default_do_thing(request, context):
        return DoThingResponse(names=[request.name])

    async def default_do_many_things(requests, context):
        return DoThingResponse(names=[request.name async for request in requests])

    async def default_get_thing_versions(request, context):
        for version in range(1, 4):
            yield GetThingResponse(name=request.name, version=version)

    async def default_get_different_things(requests, context):
        version = 0
        async for request in requests:
            version += 1
            yield GetThingResponse(name=request.name, version=version)

    return grpc.method_handlers_generic_handler(
        "service.Test",
        {
            "DoThing": grpc.unary_unary_rpc_method_handler(
                do_thing or default_do_thing,
                request_deserializer=DoThingRequest.FromString,
                response_serializer=DoThingResponse.SerializeToString,
            ),
            "DoManyThings": grpc.stream_unary_rpc_method_handler(
                do_many_things or default_do_many_things,
                request_deserializer=DoThingRequest.FromString,
                response_serializer=DoThingResponse.SerializeToString,
            ),
            "GetThingVersions": grpc.unary_stream_rpc_method_handler(
                get_thing_versions or default_get_thing_versions,
                request_deserializer=GetThingRequest.FromString,
                response_serializer=GetThingResponse.SerializeToString,
            ),
            "GetDifferentThings": grpc.stream_stream_rpc_method_handler(
                get_different_things or default_get_different_things,
                request_deserializer=GetThingRequest.FromString,
                response_serializer=GetThingResponse.SerializeToString,
            ),
        },
    )


async def async_requests(names) -> AsyncIterator[Any]:
    DoThingRequest = service_output().DoThingRequest

    for name in names:
        yield DoThingRequest(name=name)


async def assert_producer_closed(producer_closed: asyncio.Event, produced_names: list[str]) -> None:
    try:
        await asyncio.wait_for(producer_closed.wait(), timeout=1)
    except TimeoutError:
        pytest.fail(
            "request iterator was not closed after the RPC failed; "
            f"produced {len(produced_names)} request(s): {produced_names}",
        )


def make_generated_style_base():
    from aristaproto.grpcio import ServiceBase

    output = service_output()
    DoThingRequest = output.DoThingRequest
    DoThingResponse = output.DoThingResponse
    GetThingRequest = output.GetThingRequest
    GetThingResponse = output.GetThingResponse

    class TestBase(ServiceBase):
        async def do_thing(self, message: DoThingRequest) -> DoThingResponse:
            await self._grpcio_unimplemented()

        async def do_many_things(self, messages: AsyncIterator[DoThingRequest]) -> DoThingResponse:
            await self._grpcio_unimplemented()

        async def get_thing_versions(self, message: GetThingRequest) -> AsyncIterator[GetThingResponse]:
            await self._grpcio_unimplemented()
            yield GetThingResponse()

        async def get_different_things(
            self,
            messages: AsyncIterator[GetThingRequest],
        ) -> AsyncIterator[GetThingResponse]:
            await self._grpcio_unimplemented()
            yield GetThingResponse()

        def _grpcio_rpc_handler(self):
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

    return TestBase
