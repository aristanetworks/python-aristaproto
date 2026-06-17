from __future__ import annotations

import asyncio

import pytest

from tests.grpcio.fixtures import (
    GrpcioTestStub,
    assert_response_iterator_closed,
    close_tracked_get_thing_responses,
    grpcio_channel_for_service,
    service_output,
    stream_stream_response_cleanup_service,
    unary_stream_response_cleanup_service,
)
from tests.util import requires_grpcio  # noqa: F401


@pytest.mark.asyncio
async def test_request_metadata_is_available_through_context(requires_grpcio, grpcio_test_base):
    output = service_output()
    do_thing_request_type = output.DoThingRequest
    do_thing_response_type = output.DoThingResponse

    class MetadataService(grpcio_test_base):
        async def do_thing(self, message):
            metadata = dict(self._grpcio_context.invocation_metadata())
            return do_thing_response_type(names=[metadata["authorization"]])

    async with grpcio_channel_for_service(MetadataService()) as channel:
        response = await GrpcioTestStub(channel).do_thing(
            do_thing_request_type(name="ignored"),
            metadata={"authorization": "token"},
        )

    assert response.names == ["token"]


@pytest.mark.asyncio
async def test_trailing_metadata_and_explicit_status_through_context(requires_grpcio, grpcio_test_base):
    import grpc

    output = service_output()
    do_thing_request_type = output.DoThingRequest
    do_thing_response_type = output.DoThingResponse

    class StatusService(grpcio_test_base):
        async def do_thing(self, message):
            self._grpcio_context.set_trailing_metadata((("result", "blocked"),))
            self._grpcio_context.set_code(grpc.StatusCode.PERMISSION_DENIED)
            self._grpcio_context.set_details("no access")
            return do_thing_response_type(names=[message.name])

    async with grpcio_channel_for_service(StatusService()) as channel:
        call = channel.unary_unary(
            "/service.Test/DoThing",
            request_serializer=do_thing_request_type.SerializeToString,
            response_deserializer=do_thing_response_type.FromString,
        )(do_thing_request_type(name="secret"))
        with pytest.raises(grpc.aio.AioRpcError) as exc_info:
            await call

    assert exc_info.value.code() is grpc.StatusCode.PERMISSION_DENIED
    assert exc_info.value.details() == "no access"
    assert exc_info.value.trailing_metadata()["result"] == "blocked"


@pytest.mark.asyncio
async def test_context_is_isolated_across_concurrent_requests(requires_grpcio, grpcio_test_base):
    output = service_output()
    do_thing_request_type = output.DoThingRequest
    do_thing_response_type = output.DoThingResponse

    class ConcurrentService(grpcio_test_base):
        async def do_thing(self, message):
            first_context = self._grpcio_context
            await asyncio.sleep(0.01)
            assert self._grpcio_context is first_context
            metadata = dict(first_context.invocation_metadata())
            return do_thing_response_type(names=[message.name, metadata["request-id"]])

    async with grpcio_channel_for_service(ConcurrentService()) as channel:
        client = GrpcioTestStub(channel)
        responses = await asyncio.gather(
            client.do_thing(do_thing_request_type(name="one"), metadata={"request-id": "1"}),
            client.do_thing(do_thing_request_type(name="two"), metadata={"request-id": "2"}),
        )

    assert sorted(response.names for response in responses) == [["one", "1"], ["two", "2"]]


@pytest.mark.asyncio
async def test_server_streaming_response_helper_rejects_sync_iterables(requires_grpcio):
    from aristaproto.grpcio.grpcio_async_server import SERVER_STREAMING_RETURN_ERROR, _ensure_async_response_iterable

    get_thing_response_type = service_output().GetThingResponse

    responses = _ensure_async_response_iterable([get_thing_response_type(name="invalid")])

    with pytest.raises(TypeError, match=SERVER_STREAMING_RETURN_ERROR):
        await anext(responses)


@pytest.mark.asyncio
async def test_server_streaming_response_helper_rejects_awaited_response_values(requires_grpcio):
    from aristaproto.grpcio.grpcio_async_server import SERVER_STREAMING_RETURN_ERROR, _ensure_async_response_iterable

    get_thing_response_type = service_output().GetThingResponse

    async def response():
        return get_thing_response_type(name="invalid")

    responses = _ensure_async_response_iterable(response())

    with pytest.raises(TypeError, match=SERVER_STREAMING_RETURN_ERROR):
        await anext(responses)


@pytest.mark.asyncio
async def test_server_streaming_response_helper_rejects_awaited_iterables(requires_grpcio):
    from aristaproto.grpcio.grpcio_async_server import SERVER_STREAMING_RETURN_ERROR, _ensure_async_response_iterable

    get_thing_response_type = service_output().GetThingResponse

    async def responses():
        return [get_thing_response_type(name="invalid")]

    response_iterator = _ensure_async_response_iterable(responses())

    with pytest.raises(TypeError, match=SERVER_STREAMING_RETURN_ERROR):
        await anext(response_iterator)


@pytest.mark.asyncio
async def test_server_streaming_response_helper_accepts_awaited_none(requires_grpcio):
    from aristaproto.grpcio.grpcio_async_server import _ensure_async_response_iterable

    async def no_responses():
        return None

    responses = _ensure_async_response_iterable(no_responses())

    with pytest.raises(StopAsyncIteration):
        await anext(responses)


@pytest.mark.asyncio
async def test_server_streaming_response_helper_closes_async_iterables(requires_grpcio):
    from aristaproto.grpcio.grpcio_async_server import _ensure_async_response_iterable

    response_iterator_closed = asyncio.Event()
    response_iterator = _ensure_async_response_iterable(
        close_tracked_get_thing_responses("first", response_iterator_closed)
    )

    first_response = await anext(response_iterator)
    assert first_response.name == "first"

    await response_iterator.aclose()
    await assert_response_iterator_closed(response_iterator_closed)


@pytest.mark.asyncio
async def test_server_streaming_response_helper_closes_custom_async_iterators(requires_grpcio):
    from aristaproto.grpcio.grpcio_async_server import _ensure_async_response_iterable

    get_thing_response_type = service_output().GetThingResponse

    class ResponseIterator:
        def __init__(self) -> None:
            self.closed = asyncio.Event()
            self.index = 0

        def __aiter__(self):
            return self

        async def __anext__(self):
            self.index += 1
            if self.index == 1:
                return get_thing_response_type(name="first")
            await asyncio.sleep(10)
            raise StopAsyncIteration

        async def aclose(self) -> None:
            self.closed.set()

    responses = ResponseIterator()
    response_iterator = _ensure_async_response_iterable(responses)

    first_response = await anext(response_iterator)
    assert first_response.name == "first"

    await response_iterator.aclose()
    await assert_response_iterator_closed(responses.closed)


@pytest.mark.asyncio
async def test_unary_stream_client_cancellation_closes_response_iterator(requires_grpcio, grpcio_test_base):
    output = service_output()
    get_thing_request_type = output.GetThingRequest
    get_thing_response_type = output.GetThingResponse

    response_iterator_closed = asyncio.Event()

    async with grpcio_channel_for_service(
        unary_stream_response_cleanup_service(grpcio_test_base, response_iterator_closed)
    ) as channel:
        call = channel.unary_stream(
            "/service.Test/GetThingVersions",
            request_serializer=get_thing_request_type.SerializeToString,
            response_deserializer=get_thing_response_type.FromString,
        )(get_thing_request_type(name="versions"))

        first_response = await anext(call.__aiter__())
        assert (first_response.name, first_response.version) == ("versions", 1)

        call.cancel()
        await assert_response_iterator_closed(response_iterator_closed)


@pytest.mark.asyncio
async def test_stream_stream_client_cancellation_closes_response_iterator(requires_grpcio, grpcio_test_base):
    output = service_output()
    get_thing_request_type = output.GetThingRequest
    get_thing_response_type = output.GetThingResponse

    response_iterator_closed = asyncio.Event()

    async with grpcio_channel_for_service(
        stream_stream_response_cleanup_service(grpcio_test_base, response_iterator_closed)
    ) as channel:
        call = channel.stream_stream(
            "/service.Test/GetDifferentThings",
            request_serializer=get_thing_request_type.SerializeToString,
            response_deserializer=get_thing_response_type.FromString,
        )([get_thing_request_type(name="alpha")])

        first_response = await anext(call.__aiter__())
        assert (first_response.name, first_response.version) == ("alpha", 1)

        call.cancel()
        await assert_response_iterator_closed(response_iterator_closed)


@pytest.mark.asyncio
async def test_aristaproto_unary_stream_close_cancels_server_response_iterator(requires_grpcio, grpcio_test_base):
    output = service_output()
    get_thing_request_type = output.GetThingRequest

    response_iterator_closed = asyncio.Event()

    async with grpcio_channel_for_service(
        unary_stream_response_cleanup_service(grpcio_test_base, response_iterator_closed)
    ) as channel:
        responses = GrpcioTestStub(channel).get_thing_versions(get_thing_request_type(name="versions"))

        first_response = await anext(responses)
        assert (first_response.name, first_response.version) == ("versions", 1)

        await responses.aclose()
        await assert_response_iterator_closed(response_iterator_closed)


@pytest.mark.asyncio
async def test_aristaproto_stream_stream_close_cancels_server_response_iterator(requires_grpcio, grpcio_test_base):
    output = service_output()
    get_thing_request_type = output.GetThingRequest

    response_iterator_closed = asyncio.Event()

    async with grpcio_channel_for_service(
        stream_stream_response_cleanup_service(grpcio_test_base, response_iterator_closed)
    ) as channel:
        responses = GrpcioTestStub(channel).get_different_things([get_thing_request_type(name="alpha")])

        first_response = await anext(responses)
        assert (first_response.name, first_response.version) == ("alpha", 1)

        await responses.aclose()
        await assert_response_iterator_closed(response_iterator_closed)
