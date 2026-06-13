from __future__ import annotations

import asyncio

import pytest

from tests.grpcio.fixtures import (
    GrpcioTestStub,
    assert_producer_closed,
    async_requests,
    grpcio_channel_for_handler,
    grpcio_test_handler,
    service_output,
)
from tests.util import requires_grpcio  # noqa: F401


@pytest.mark.asyncio
async def test_unary_unary(requires_grpcio):
    DoThingRequest = service_output().DoThingRequest

    async with grpcio_channel_for_handler(grpcio_test_handler()) as channel:
        response = await GrpcioTestStub(channel).do_thing(DoThingRequest(name="clean room"))

    assert response.names == ["clean room"]


@pytest.mark.asyncio
async def test_unary_stream(requires_grpcio):
    GetThingRequest = service_output().GetThingRequest

    async with grpcio_channel_for_handler(grpcio_test_handler()) as channel:
        responses = [
            response async for response in GrpcioTestStub(channel).get_thing_versions(GetThingRequest(name="change"))
        ]

    assert [(response.name, response.version) for response in responses] == [
        ("change", 1),
        ("change", 2),
        ("change", 3),
    ]


@pytest.mark.asyncio
async def test_stream_unary_accepts_sync_request_iterable(requires_grpcio):
    DoThingRequest = service_output().DoThingRequest

    requests = [DoThingRequest(name="one"), DoThingRequest(name="two")]
    async with grpcio_channel_for_handler(grpcio_test_handler()) as channel:
        response = await GrpcioTestStub(channel).do_many_things(requests)

    assert response.names == ["one", "two"]


@pytest.mark.asyncio
async def test_stream_unary_accepts_async_request_iterable(requires_grpcio):
    async with grpcio_channel_for_handler(grpcio_test_handler()) as channel:
        response = await GrpcioTestStub(channel).do_many_things(async_requests(["three", "four"]))

    assert response.names == ["three", "four"]


@pytest.mark.asyncio
async def test_stream_stream(requires_grpcio):
    GetThingRequest = service_output().GetThingRequest

    requests = [GetThingRequest(name="alpha"), GetThingRequest(name="beta")]
    async with grpcio_channel_for_handler(grpcio_test_handler()) as channel:
        responses = [response async for response in GrpcioTestStub(channel).get_different_things(requests)]

    assert [(response.name, response.version) for response in responses] == [("alpha", 1), ("beta", 2)]


@pytest.mark.asyncio
async def test_metadata_override_precedence(requires_grpcio):
    output = service_output()
    DoThingRequest = output.DoThingRequest
    DoThingResponse = output.DoThingResponse

    async def do_thing(request, context):
        metadata = dict(context.invocation_metadata())
        return DoThingResponse(names=[metadata["authorization"]])

    async with grpcio_channel_for_handler(grpcio_test_handler(do_thing=do_thing)) as channel:
        client = GrpcioTestStub(channel, metadata={"authorization": "default"})
        response = await client.do_thing(
            DoThingRequest(name="ignored"),
            metadata=(("authorization", "override"),),
        )

    assert response.names == ["override"]


@pytest.mark.asyncio
async def test_timeout_override_precedence_with_deadline_exceeded(requires_grpcio):
    import grpc

    output = service_output()
    DoThingRequest = output.DoThingRequest
    DoThingResponse = output.DoThingResponse

    async def slow_do_thing(request, context):
        await asyncio.sleep(0.1)
        return DoThingResponse(names=[request.name])

    async with grpcio_channel_for_handler(grpcio_test_handler(do_thing=slow_do_thing)) as channel:
        client = GrpcioTestStub(channel, timeout=5)
        with pytest.raises(grpc.aio.AioRpcError) as exc_info:
            await client.do_thing(DoThingRequest(name="too late"), timeout=0.001)

    assert exc_info.value.code() is grpc.StatusCode.DEADLINE_EXCEEDED


@pytest.mark.asyncio
async def test_grpcio_native_error_propagation(requires_grpcio):
    import grpc

    DoThingRequest = service_output().DoThingRequest

    async def do_thing(request, context):
        await context.abort(grpc.StatusCode.UNAUTHENTICATED, "missing auth")

    async with grpcio_channel_for_handler(grpcio_test_handler(do_thing=do_thing)) as channel:
        with pytest.raises(grpc.aio.AioRpcError) as exc_info:
            await GrpcioTestStub(channel).do_thing(DoThingRequest(name="blocked"))

    assert exc_info.value.code() is grpc.StatusCode.UNAUTHENTICATED


@pytest.mark.asyncio
async def test_stream_stream_server_error_closes_request_iterator(requires_grpcio):
    import grpc

    output = service_output()
    GetThingRequest = output.GetThingRequest
    GetThingResponse = output.GetThingResponse

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

    async with grpcio_channel_for_handler(grpcio_test_handler(get_different_things=get_different_things)) as channel:
        responses = GrpcioTestStub(channel).get_different_things(requests())

        first_response = await anext(responses)
        assert (first_response.name, first_response.version) == ("request-1", 1)

        with pytest.raises(grpc.aio.AioRpcError) as exc_info:
            await anext(responses)

        assert exc_info.value.code() is grpc.StatusCode.INVALID_ARGUMENT
        await assert_producer_closed(producer_closed, produced_names)

    assert produced_names


@pytest.mark.asyncio
async def test_stream_stream_response_iterator_close_closes_request_iterator(requires_grpcio):
    output = service_output()
    GetThingRequest = output.GetThingRequest
    GetThingResponse = output.GetThingResponse

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

    async with grpcio_channel_for_handler(grpcio_test_handler(get_different_things=get_different_things)) as channel:
        responses = GrpcioTestStub(channel).get_different_things(requests())

        first_response = await anext(responses)
        assert (first_response.name, first_response.version) == ("request-1", 1)

        await responses.aclose()
        await assert_producer_closed(producer_closed, produced_names)

    assert produced_names


@pytest.mark.asyncio
async def test_stream_unary_server_error_closes_request_iterator(requires_grpcio):
    import grpc

    DoThingRequest = service_output().DoThingRequest

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

    async with grpcio_channel_for_handler(grpcio_test_handler(do_many_things=do_many_things)) as channel:
        with pytest.raises(grpc.aio.AioRpcError) as exc_info:
            await GrpcioTestStub(channel).do_many_things(requests())

        assert exc_info.value.code() is grpc.StatusCode.INVALID_ARGUMENT
        await assert_producer_closed(producer_closed, produced_names)

    assert produced_names
