from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest

from tests.util import requires_grpcio  # noqa: F401


class TestGrpcioAsyncStub:
    def __init__(self, channel, **kwargs):
        from aristaproto.grpcio import ServiceStub

        self._stub = ServiceStub(channel, **kwargs)

    async def do_thing(self, message, **kwargs):
        from tests.outputs.service.service import DoThingResponse

        return await self._stub._unary_unary(
            "/service.Test/DoThing",
            message,
            DoThingResponse,
            **kwargs,
        )

    async def do_many_things(self, messages, **kwargs):
        from tests.outputs.service.service import DoThingRequest, DoThingResponse

        return await self._stub._stream_unary(
            "/service.Test/DoManyThings",
            messages,
            DoThingRequest,
            DoThingResponse,
            **kwargs,
        )

    async def get_thing_versions(self, message, **kwargs):
        from tests.outputs.service.service import GetThingResponse

        async for response in self._stub._unary_stream(
            "/service.Test/GetThingVersions",
            message,
            GetThingResponse,
            **kwargs,
        ):
            yield response

    async def get_different_things(self, messages, **kwargs):
        from tests.outputs.service.service import GetThingRequest, GetThingResponse

        async for response in self._stub._stream_stream(
            "/service.Test/GetDifferentThings",
            messages,
            GetThingRequest,
            GetThingResponse,
            **kwargs,
        ):
            yield response


@asynccontextmanager
async def _grpcio_channel(handler) -> AsyncIterator:
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


def _test_handler(
    *,
    do_thing=None,
    do_many_things=None,
    get_thing_versions=None,
    get_different_things=None,
):
    import grpc

    from tests.outputs.service.service import (
        DoThingRequest,
        DoThingResponse,
        GetThingRequest,
        GetThingResponse,
    )

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


async def _async_requests(names):
    from tests.outputs.service.service import DoThingRequest

    for name in names:
        yield DoThingRequest(name=name)


async def _assert_producer_closed(producer_closed: asyncio.Event, produced_names: list[str]) -> None:
    try:
        await asyncio.wait_for(producer_closed.wait(), timeout=1)
    except TimeoutError:
        pytest.fail(
            "request iterator was not closed after the RPC failed; "
            f"produced {len(produced_names)} request(s): {produced_names}",
        )


@pytest.mark.asyncio
async def test_unary_unary(requires_grpcio):
    from tests.outputs.service.service import DoThingRequest

    async with _grpcio_channel(_test_handler()) as channel:
        response = await TestGrpcioAsyncStub(channel).do_thing(DoThingRequest(name="clean room"))

    assert response.names == ["clean room"]


@pytest.mark.asyncio
async def test_unary_stream(requires_grpcio):
    from tests.outputs.service.service import GetThingRequest

    async with _grpcio_channel(_test_handler()) as channel:
        responses = [
            response
            async for response in TestGrpcioAsyncStub(channel).get_thing_versions(GetThingRequest(name="change"))
        ]

    assert [(response.name, response.version) for response in responses] == [
        ("change", 1),
        ("change", 2),
        ("change", 3),
    ]


@pytest.mark.asyncio
async def test_stream_unary_accepts_sync_request_iterable(requires_grpcio):
    from tests.outputs.service.service import DoThingRequest

    requests = [DoThingRequest(name="one"), DoThingRequest(name="two")]
    async with _grpcio_channel(_test_handler()) as channel:
        response = await TestGrpcioAsyncStub(channel).do_many_things(requests)

    assert response.names == ["one", "two"]


@pytest.mark.asyncio
async def test_stream_unary_accepts_async_request_iterable(requires_grpcio):
    async with _grpcio_channel(_test_handler()) as channel:
        response = await TestGrpcioAsyncStub(channel).do_many_things(_async_requests(["three", "four"]))

    assert response.names == ["three", "four"]


@pytest.mark.asyncio
async def test_stream_stream(requires_grpcio):
    from tests.outputs.service.service import GetThingRequest

    requests = [GetThingRequest(name="alpha"), GetThingRequest(name="beta")]
    async with _grpcio_channel(_test_handler()) as channel:
        responses = [response async for response in TestGrpcioAsyncStub(channel).get_different_things(requests)]

    assert [(response.name, response.version) for response in responses] == [("alpha", 1), ("beta", 2)]


@pytest.mark.asyncio
async def test_metadata_override_precedence(requires_grpcio):
    from tests.outputs.service.service import DoThingRequest, DoThingResponse

    async def do_thing(request, context):
        metadata = dict(context.invocation_metadata())
        return DoThingResponse(names=[metadata["authorization"]])

    async with _grpcio_channel(_test_handler(do_thing=do_thing)) as channel:
        client = TestGrpcioAsyncStub(channel, metadata={"authorization": "default"})
        response = await client.do_thing(
            DoThingRequest(name="ignored"),
            metadata=(("authorization", "override"),),
        )

    assert response.names == ["override"]


@pytest.mark.asyncio
async def test_timeout_override_precedence_with_deadline_exceeded(requires_grpcio):
    import grpc

    from tests.outputs.service.service import DoThingRequest, DoThingResponse

    async def slow_do_thing(request, context):
        await asyncio.sleep(0.1)
        return DoThingResponse(names=[request.name])

    async with _grpcio_channel(_test_handler(do_thing=slow_do_thing)) as channel:
        client = TestGrpcioAsyncStub(channel, timeout=5)
        with pytest.raises(grpc.aio.AioRpcError) as exc_info:
            await client.do_thing(DoThingRequest(name="too late"), timeout=0.001)

    assert exc_info.value.code() is grpc.StatusCode.DEADLINE_EXCEEDED


@pytest.mark.asyncio
async def test_grpcio_native_error_propagation(requires_grpcio):
    import grpc

    from tests.outputs.service.service import DoThingRequest

    async def do_thing(request, context):
        await context.abort(grpc.StatusCode.UNAUTHENTICATED, "missing auth")

    async with _grpcio_channel(_test_handler(do_thing=do_thing)) as channel:
        with pytest.raises(grpc.aio.AioRpcError) as exc_info:
            await TestGrpcioAsyncStub(channel).do_thing(DoThingRequest(name="blocked"))

    assert exc_info.value.code() is grpc.StatusCode.UNAUTHENTICATED


@pytest.mark.asyncio
async def test_stream_stream_server_error_closes_request_iterator(requires_grpcio):
    import grpc

    from tests.outputs.service.service import GetThingRequest, GetThingResponse

    producer_closed = asyncio.Event()
    produced_names: list[str] = []

    async def requests():
        try:
            index = 0
            while True:
                index += 1
                name = f"request-{index}"
                produced_names.append(name)
                yield GetThingRequest(name=name)
                await asyncio.sleep(0.01)
        finally:
            producer_closed.set()

    async def get_different_things(requests, context):
        first_request = await anext(requests)
        yield GetThingResponse(name=first_request.name, version=1)
        await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "server stopped reading")

    async with _grpcio_channel(_test_handler(get_different_things=get_different_things)) as channel:
        responses = TestGrpcioAsyncStub(channel).get_different_things(requests())

        first_response = await anext(responses)
        assert (first_response.name, first_response.version) == ("request-1", 1)

        with pytest.raises(grpc.aio.AioRpcError) as exc_info:
            await anext(responses)

        assert exc_info.value.code() is grpc.StatusCode.INVALID_ARGUMENT
        await _assert_producer_closed(producer_closed, produced_names)

    assert produced_names


@pytest.mark.asyncio
async def test_stream_stream_response_iterator_close_closes_request_iterator(requires_grpcio):
    from tests.outputs.service.service import GetThingRequest, GetThingResponse

    producer_closed = asyncio.Event()
    produced_names: list[str] = []

    async def requests():
        try:
            index = 0
            while True:
                index += 1
                name = f"request-{index}"
                produced_names.append(name)
                yield GetThingRequest(name=name)
                await asyncio.sleep(0.01)
        finally:
            producer_closed.set()

    async def get_different_things(requests, context):
        first_request = await anext(requests)
        yield GetThingResponse(name=first_request.name, version=1)
        await asyncio.sleep(10)

    async with _grpcio_channel(_test_handler(get_different_things=get_different_things)) as channel:
        responses = TestGrpcioAsyncStub(channel).get_different_things(requests())

        first_response = await anext(responses)
        assert (first_response.name, first_response.version) == ("request-1", 1)

        await responses.aclose()
        await _assert_producer_closed(producer_closed, produced_names)

    assert produced_names


@pytest.mark.asyncio
async def test_stream_unary_server_error_closes_request_iterator(requires_grpcio):
    import grpc

    from tests.outputs.service.service import DoThingRequest

    producer_closed = asyncio.Event()
    produced_names: list[str] = []

    async def requests():
        try:
            index = 0
            while True:
                index += 1
                name = f"request-{index}"
                produced_names.append(name)
                yield DoThingRequest(name=name)
                await asyncio.sleep(0.01)
        finally:
            producer_closed.set()

    async def do_many_things(requests, context):
        await anext(requests)
        await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "server stopped reading")

    async with _grpcio_channel(_test_handler(do_many_things=do_many_things)) as channel:
        with pytest.raises(grpc.aio.AioRpcError) as exc_info:
            await TestGrpcioAsyncStub(channel).do_many_things(requests())

        assert exc_info.value.code() is grpc.StatusCode.INVALID_ARGUMENT
        await _assert_producer_closed(producer_closed, produced_names)

    assert produced_names
