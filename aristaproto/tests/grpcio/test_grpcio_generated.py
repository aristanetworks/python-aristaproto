from __future__ import annotations

import importlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest

from tests.util import requires_grpcio  # noqa: F401

SERVICE_OUTPUT = "tests.outputs.service_client_async_transport_grpcio_server_async_transport_grpcio.service"
IMPORT_SERVICE_OUTPUT = (
    "tests.outputs.import_service_input_message_client_async_transport_grpcio_server_async_transport_grpcio."
    "import_service_input_message"
)
SEPARATE_PACKAGE_OUTPUT = (
    "tests.outputs.service_separate_packages_client_async_transport_grpcio_server_async_transport_grpcio."
    "service_separate_packages.things"
)


@asynccontextmanager
async def grpcio_channel(service) -> AsyncIterator:
    import grpc

    server = grpc.aio.server()
    server.add_generic_rpc_handlers((service._grpcio_rpc_handler(),))
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
async def grpcio_raw_channel(handler) -> AsyncIterator:
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


@pytest.mark.asyncio
async def test_generated_grpcio_async_service_supports_all_cardinalities(requires_grpcio) -> None:
    output = importlib.import_module(SERVICE_OUTPUT)
    DoThingRequest = output.DoThingRequest
    DoThingResponse = output.DoThingResponse
    GetThingRequest = output.GetThingRequest
    GetThingResponse = output.GetThingResponse
    TestBase = output.TestBase
    TestStub = output.TestStub

    class Service(TestBase):
        async def do_thing(self, message):
            return DoThingResponse(names=[message.name])

        async def do_many_things(self, messages):
            return DoThingResponse(names=[message.name async for message in messages])

        async def get_thing_versions(self, message):
            for version in range(1, 4):
                yield GetThingResponse(name=message.name, version=version)

        async def get_different_things(self, messages):
            version = 0
            async for message in messages:
                version += 1
                yield GetThingResponse(name=message.name, version=version)

    async with grpcio_channel(Service()) as channel:
        client = TestStub(channel)
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
async def test_generated_grpcio_async_unimplemented_base_returns_unimplemented(requires_grpcio) -> None:
    import grpc

    output = importlib.import_module(SERVICE_OUTPUT)
    DoThingRequest = output.DoThingRequest
    GetThingRequest = output.GetThingRequest
    TestBase = output.TestBase
    TestStub = output.TestStub

    async with grpcio_channel(TestBase()) as channel:
        client = TestStub(channel)

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
async def test_generated_grpcio_async_service_imported_messages_round_trip(requires_grpcio) -> None:
    output = importlib.import_module(IMPORT_SERVICE_OUTPUT)
    child_output = importlib.import_module(f"{IMPORT_SERVICE_OUTPUT}.child")
    ChildRequestMessage = child_output.ChildRequestMessage
    NestedRequestMessage = output.NestedRequestMessage
    RequestMessage = output.RequestMessage
    RequestResponse = output.RequestResponse
    TestBase = output.TestBase
    TestStub = output.TestStub

    class Service(TestBase):
        async def do_thing(self, message):
            return RequestResponse(value=message.argument)

        async def do_thing_2(self, message):
            return RequestResponse(value=message.child_argument)

        async def do_thing_3(self, message):
            return RequestResponse(value=message.nested_argument)

    async with grpcio_channel(Service()) as channel:
        client = TestStub(channel)
        response = await client.do_thing(RequestMessage(argument=11))
        child_response = await client.do_thing_2(ChildRequestMessage(child_argument=22))
        nested_response = await client.do_thing_3(NestedRequestMessage(nested_argument=33))

    assert response.value == 11
    assert child_response.value == 22
    assert nested_response.value == 33


@pytest.mark.asyncio
async def test_generated_grpcio_async_separate_package_imports_round_trip(requires_grpcio) -> None:
    messages = importlib.import_module(f"{SEPARATE_PACKAGE_OUTPUT}.messages")
    service = importlib.import_module(f"{SEPARATE_PACKAGE_OUTPUT}.service")
    TestBase = service.TestBase
    TestStub = service.TestStub

    class Service(TestBase):
        async def do_thing(self, message):
            return messages.DoThingResponse(names=[message.name])

        async def do_many_things(self, request_messages):
            return messages.DoThingResponse(names=[message.name async for message in request_messages])

        async def get_thing_versions(self, message):
            for version in range(1, 3):
                yield messages.GetThingResponse(name=message.name, version=version)

        async def get_different_things(self, request_messages):
            version = 0
            async for message in request_messages:
                version += 1
                yield messages.GetThingResponse(name=message.name, version=version)

    async with grpcio_channel(Service()) as channel:
        client = TestStub(channel)
        unary = await client.do_thing(messages.DoThingRequest(name="external"))
        stream_unary = await client.do_many_things(
            [messages.DoThingRequest(name="first"), messages.DoThingRequest(name="second")]
        )
        unary_stream = [
            response async for response in client.get_thing_versions(messages.GetThingRequest(name="versions"))
        ]
        stream_stream = [
            response
            async for response in client.get_different_things(
                [messages.GetThingRequest(name="alpha"), messages.GetThingRequest(name="beta")]
            )
        ]

    assert unary.names == ["external"]
    assert stream_unary.names == ["first", "second"]
    assert [(response.name, response.version) for response in unary_stream] == [("versions", 1), ("versions", 2)]
    assert [(response.name, response.version) for response in stream_stream] == [("alpha", 1), ("beta", 2)]


@pytest.mark.asyncio
async def test_generated_grpcio_async_deprecated_stub_method_warns_once(requires_grpcio) -> None:
    import grpc

    from tests.outputs.deprecated_client_async_transport_grpcio.deprecated import Empty, TestServiceStub

    async def deprecated_func(request, context):
        return Empty()

    handler = grpc.method_handlers_generic_handler(
        "deprecated.TestService",
        {
            "deprecated_func": grpc.unary_unary_rpc_method_handler(
                deprecated_func,
                request_deserializer=Empty.FromString,
                response_serializer=Empty.SerializeToString,
            )
        },
    )

    async with grpcio_raw_channel(handler) as channel:
        with pytest.warns(DeprecationWarning) as warnings:
            response = await TestServiceStub(channel).deprecated_func()

    assert response == Empty()
    assert len(warnings) == 1
