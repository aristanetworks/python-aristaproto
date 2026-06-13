from __future__ import annotations

import asyncio

import pytest

from tests.grpcio.fixtures import GrpcioTestStub, grpcio_channel_for_service, service_output
from tests.util import requires_grpcio  # noqa: F401


@pytest.mark.asyncio
async def test_all_cardinalities(requires_grpcio, grpcio_working_service):
    output = service_output()
    DoThingRequest = output.DoThingRequest
    GetThingRequest = output.GetThingRequest

    async with grpcio_channel_for_service(grpcio_working_service) as channel:
        client = GrpcioTestStub(channel)

        unary = await client.do_thing(DoThingRequest(name="single"))
        stream_unary = await client.do_many_things([DoThingRequest(name="one"), DoThingRequest(name="two")])
        unary_stream = [response async for response in client.get_thing_versions(GetThingRequest(name="versions"))]
        stream_stream = [
            response
            async for response in client.get_different_things(
                [GetThingRequest(name="alpha"), GetThingRequest(name="beta")]
            )
        ]

    assert unary.names == ["single"]
    assert stream_unary.names == ["one", "two"]
    assert [(response.name, response.version) for response in unary_stream] == [
        ("versions", 1),
        ("versions", 2),
        ("versions", 3),
    ]
    assert [(response.name, response.version) for response in stream_stream] == [("alpha", 1), ("beta", 2)]


@pytest.mark.asyncio
async def test_request_metadata_is_available_through_context(requires_grpcio, grpcio_test_base):
    output = service_output()
    DoThingRequest = output.DoThingRequest
    DoThingResponse = output.DoThingResponse

    class MetadataService(grpcio_test_base):
        async def do_thing(self, message):
            metadata = dict(self._grpcio_context.invocation_metadata())
            return DoThingResponse(names=[metadata["authorization"]])

    async with grpcio_channel_for_service(MetadataService()) as channel:
        response = await GrpcioTestStub(channel).do_thing(
            DoThingRequest(name="ignored"),
            metadata={"authorization": "token"},
        )

    assert response.names == ["token"]


@pytest.mark.asyncio
async def test_trailing_metadata_and_explicit_status_through_context(requires_grpcio, grpcio_test_base):
    import grpc

    output = service_output()
    DoThingRequest = output.DoThingRequest
    DoThingResponse = output.DoThingResponse

    class StatusService(grpcio_test_base):
        async def do_thing(self, message):
            self._grpcio_context.set_trailing_metadata((("result", "blocked"),))
            self._grpcio_context.set_code(grpc.StatusCode.PERMISSION_DENIED)
            self._grpcio_context.set_details("no access")
            return DoThingResponse(names=[message.name])

    async with grpcio_channel_for_service(StatusService()) as channel:
        call = channel.unary_unary(
            "/service.Test/DoThing",
            request_serializer=DoThingRequest.SerializeToString,
            response_deserializer=DoThingResponse.FromString,
        )(DoThingRequest(name="secret"))
        with pytest.raises(grpc.aio.AioRpcError) as exc_info:
            await call

    assert exc_info.value.code() is grpc.StatusCode.PERMISSION_DENIED
    assert exc_info.value.details() == "no access"
    assert exc_info.value.trailing_metadata()["result"] == "blocked"


@pytest.mark.asyncio
async def test_context_is_isolated_across_concurrent_requests(requires_grpcio, grpcio_test_base):
    output = service_output()
    DoThingRequest = output.DoThingRequest
    DoThingResponse = output.DoThingResponse

    class ConcurrentService(grpcio_test_base):
        async def do_thing(self, message):
            first_context = self._grpcio_context
            await asyncio.sleep(0.01)
            assert self._grpcio_context is first_context
            metadata = dict(first_context.invocation_metadata())
            return DoThingResponse(names=[message.name, metadata["request-id"]])

    async with grpcio_channel_for_service(ConcurrentService()) as channel:
        client = GrpcioTestStub(channel)
        responses = await asyncio.gather(
            client.do_thing(DoThingRequest(name="one"), metadata={"request-id": "1"}),
            client.do_thing(DoThingRequest(name="two"), metadata={"request-id": "2"}),
        )

    assert sorted(response.names for response in responses) == [["one", "1"], ["two", "2"]]


@pytest.mark.asyncio
async def test_unimplemented_base_methods_return_unimplemented(requires_grpcio, grpcio_test_base):
    import grpc

    output = service_output()
    DoThingRequest = output.DoThingRequest
    GetThingRequest = output.GetThingRequest

    async with grpcio_channel_for_service(grpcio_test_base()) as channel:
        client = GrpcioTestStub(channel)
        with pytest.raises(grpc.aio.AioRpcError) as exc_info:
            await client.do_thing(DoThingRequest(name="missing"))
        assert exc_info.value.code() is grpc.StatusCode.UNIMPLEMENTED

        with pytest.raises(grpc.aio.AioRpcError) as exc_info:
            await client.do_many_things([DoThingRequest(name="missing")])
        assert exc_info.value.code() is grpc.StatusCode.UNIMPLEMENTED

        with pytest.raises(grpc.aio.AioRpcError) as exc_info:
            responses = client.get_thing_versions(GetThingRequest(name="missing"))
            await anext(responses)
        assert exc_info.value.code() is grpc.StatusCode.UNIMPLEMENTED

        with pytest.raises(grpc.aio.AioRpcError) as exc_info:
            responses = client.get_different_things([GetThingRequest(name="missing")])
            await anext(responses)
        assert exc_info.value.code() is grpc.StatusCode.UNIMPLEMENTED


@pytest.mark.asyncio
async def test_server_streaming_response_helper_rejects_sync_iterables(requires_grpcio):
    from aristaproto.grpcio.grpcio_async_server import SERVER_STREAMING_RETURN_ERROR, _ensure_async_response_iterable

    GetThingResponse = service_output().GetThingResponse

    responses = _ensure_async_response_iterable([GetThingResponse(name="invalid")])

    with pytest.raises(TypeError, match=SERVER_STREAMING_RETURN_ERROR):
        await anext(responses)


@pytest.mark.asyncio
async def test_server_streaming_response_helper_rejects_awaited_response_values(requires_grpcio):
    from aristaproto.grpcio.grpcio_async_server import SERVER_STREAMING_RETURN_ERROR, _ensure_async_response_iterable

    GetThingResponse = service_output().GetThingResponse

    async def response():
        return GetThingResponse(name="invalid")

    responses = _ensure_async_response_iterable(response())

    with pytest.raises(TypeError, match=SERVER_STREAMING_RETURN_ERROR):
        await anext(responses)


@pytest.mark.asyncio
async def test_server_streaming_response_helper_rejects_awaited_iterables(requires_grpcio):
    from aristaproto.grpcio.grpcio_async_server import SERVER_STREAMING_RETURN_ERROR, _ensure_async_response_iterable

    GetThingResponse = service_output().GetThingResponse

    async def responses():
        return [GetThingResponse(name="invalid")]

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

    GetThingResponse = service_output().GetThingResponse

    response_iterator_closed = asyncio.Event()

    async def responses():
        try:
            yield GetThingResponse(name="first")
            await asyncio.sleep(10)
        finally:
            response_iterator_closed.set()

    response_iterator = _ensure_async_response_iterable(responses())

    first_response = await anext(response_iterator)
    assert first_response.name == "first"

    await response_iterator.aclose()
    await asyncio.wait_for(response_iterator_closed.wait(), timeout=1)


@pytest.mark.asyncio
async def test_server_streaming_response_helper_closes_custom_async_iterators(requires_grpcio):
    from aristaproto.grpcio.grpcio_async_server import _ensure_async_response_iterable

    GetThingResponse = service_output().GetThingResponse

    class ResponseIterator:
        def __init__(self) -> None:
            self.closed = asyncio.Event()
            self.index = 0

        def __aiter__(self):
            return self

        async def __anext__(self):
            self.index += 1
            if self.index == 1:
                return GetThingResponse(name="first")
            await asyncio.sleep(10)
            raise StopAsyncIteration

        async def aclose(self) -> None:
            self.closed.set()

    responses = ResponseIterator()
    response_iterator = _ensure_async_response_iterable(responses)

    first_response = await anext(response_iterator)
    assert first_response.name == "first"

    await response_iterator.aclose()
    await asyncio.wait_for(responses.closed.wait(), timeout=1)


@pytest.mark.asyncio
async def test_unary_stream_client_cancellation_closes_response_iterator(requires_grpcio, grpcio_test_base):
    output = service_output()
    GetThingRequest = output.GetThingRequest
    GetThingResponse = output.GetThingResponse

    response_iterator_closed = asyncio.Event()

    class ResponseCleanupService(grpcio_test_base):
        async def get_thing_versions(self, message):
            try:
                yield GetThingResponse(name=message.name, version=1)
                await asyncio.sleep(10)
            finally:
                response_iterator_closed.set()

    async with grpcio_channel_for_service(ResponseCleanupService()) as channel:
        call = channel.unary_stream(
            "/service.Test/GetThingVersions",
            request_serializer=GetThingRequest.SerializeToString,
            response_deserializer=GetThingResponse.FromString,
        )(GetThingRequest(name="versions"))

        first_response = await anext(call.__aiter__())
        assert (first_response.name, first_response.version) == ("versions", 1)

        call.cancel()
        await asyncio.wait_for(response_iterator_closed.wait(), timeout=1)


@pytest.mark.asyncio
async def test_stream_stream_client_cancellation_closes_response_iterator(requires_grpcio, grpcio_test_base):
    output = service_output()
    GetThingRequest = output.GetThingRequest
    GetThingResponse = output.GetThingResponse

    response_iterator_closed = asyncio.Event()

    class ResponseCleanupService(grpcio_test_base):
        async def get_different_things(self, messages):
            first_message = await anext(messages)
            try:
                yield GetThingResponse(name=first_message.name, version=1)
                await asyncio.sleep(10)
            finally:
                response_iterator_closed.set()

    async with grpcio_channel_for_service(ResponseCleanupService()) as channel:
        call = channel.stream_stream(
            "/service.Test/GetDifferentThings",
            request_serializer=GetThingRequest.SerializeToString,
            response_deserializer=GetThingResponse.FromString,
        )([GetThingRequest(name="alpha")])

        first_response = await anext(call.__aiter__())
        assert (first_response.name, first_response.version) == ("alpha", 1)

        call.cancel()
        await asyncio.wait_for(response_iterator_closed.wait(), timeout=1)


@pytest.mark.asyncio
async def test_aristaproto_unary_stream_close_cancels_server_response_iterator(requires_grpcio, grpcio_test_base):
    output = service_output()
    GetThingRequest = output.GetThingRequest
    GetThingResponse = output.GetThingResponse

    response_iterator_closed = asyncio.Event()

    class ResponseCleanupService(grpcio_test_base):
        async def get_thing_versions(self, message):
            try:
                yield GetThingResponse(name=message.name, version=1)
                await asyncio.sleep(10)
            finally:
                response_iterator_closed.set()

    async with grpcio_channel_for_service(ResponseCleanupService()) as channel:
        responses = GrpcioTestStub(channel).get_thing_versions(GetThingRequest(name="versions"))

        first_response = await anext(responses)
        assert (first_response.name, first_response.version) == ("versions", 1)

        await responses.aclose()
        await asyncio.wait_for(response_iterator_closed.wait(), timeout=1)


@pytest.mark.asyncio
async def test_aristaproto_stream_stream_close_cancels_server_response_iterator(requires_grpcio, grpcio_test_base):
    output = service_output()
    GetThingRequest = output.GetThingRequest
    GetThingResponse = output.GetThingResponse

    response_iterator_closed = asyncio.Event()

    class ResponseCleanupService(grpcio_test_base):
        async def get_different_things(self, messages):
            first_message = await anext(messages)
            try:
                yield GetThingResponse(name=first_message.name, version=1)
                await asyncio.sleep(10)
            finally:
                response_iterator_closed.set()

    async with grpcio_channel_for_service(ResponseCleanupService()) as channel:
        responses = GrpcioTestStub(channel).get_different_things([GetThingRequest(name="alpha")])

        first_response = await anext(responses)
        assert (first_response.name, first_response.version) == ("alpha", 1)

        await responses.aclose()
        await asyncio.wait_for(response_iterator_closed.wait(), timeout=1)
