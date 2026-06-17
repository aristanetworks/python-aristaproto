from __future__ import annotations

import importlib

import pytest

from tests.grpcio.fixtures import grpcio_channel_for_handler, grpcio_channel_for_service, service_output
from tests.util import requires_grpcio  # noqa: F401

IMPORT_SERVICE_OUTPUT = (
    "tests.outputs.import_service_input_message_client_async_transport_grpcio_server_async_transport_grpcio."
    "import_service_input_message"
)
SEPARATE_PACKAGE_OUTPUT = (
    "tests.outputs.service_separate_packages_client_async_transport_grpcio_server_async_transport_grpcio."
    "service_separate_packages.things"
)


@pytest.mark.asyncio
async def test_generated_grpcio_async_service_supports_all_cardinalities(requires_grpcio) -> None:
    output = service_output()
    do_thing_request_type = output.DoThingRequest
    do_thing_response_type = output.DoThingResponse
    get_thing_request_type = output.GetThingRequest
    get_thing_response_type = output.GetThingResponse
    test_base_type = output.TestBase
    test_stub_type = output.TestStub

    class Service(test_base_type):
        async def do_thing(self, message):
            return do_thing_response_type(names=[message.name])

        async def do_many_things(self, messages):
            return do_thing_response_type(names=[message.name async for message in messages])

        async def get_thing_versions(self, message):
            for version in range(1, 4):
                yield get_thing_response_type(name=message.name, version=version)

        async def get_different_things(self, messages):
            version = 0
            async for message in messages:
                version += 1
                yield get_thing_response_type(name=message.name, version=version)

    async with grpcio_channel_for_service(Service()) as channel:
        client = test_stub_type(channel)
        unary = await client.do_thing(do_thing_request_type(name="single"))
        stream_unary = await client.do_many_things(
            [do_thing_request_type(name="one"), do_thing_request_type(name="two")]
        )
        unary_stream = [
            response async for response in client.get_thing_versions(get_thing_request_type(name="versions"))
        ]
        stream_stream = [
            response
            async for response in client.get_different_things(
                [get_thing_request_type(name="alpha"), get_thing_request_type(name="beta")]
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

    output = service_output()
    do_thing_request_type = output.DoThingRequest
    get_thing_request_type = output.GetThingRequest
    test_base_type = output.TestBase
    test_stub_type = output.TestStub

    async with grpcio_channel_for_service(test_base_type()) as channel:
        client = test_stub_type(channel)

        with pytest.raises(grpc.aio.AioRpcError) as exc_info:
            await client.do_thing(do_thing_request_type(name="missing"))
        assert exc_info.value.code() is grpc.StatusCode.UNIMPLEMENTED

        with pytest.raises(grpc.aio.AioRpcError) as exc_info:
            await client.do_many_things([do_thing_request_type(name="missing")])
        assert exc_info.value.code() is grpc.StatusCode.UNIMPLEMENTED

        with pytest.raises(grpc.aio.AioRpcError) as exc_info:
            responses = client.get_thing_versions(get_thing_request_type(name="missing"))
            await anext(responses)
        assert exc_info.value.code() is grpc.StatusCode.UNIMPLEMENTED

        with pytest.raises(grpc.aio.AioRpcError) as exc_info:
            responses = client.get_different_things([get_thing_request_type(name="missing")])
            await anext(responses)
        assert exc_info.value.code() is grpc.StatusCode.UNIMPLEMENTED


@pytest.mark.asyncio
async def test_generated_grpcio_async_service_imported_messages_round_trip(requires_grpcio) -> None:
    output = importlib.import_module(IMPORT_SERVICE_OUTPUT)
    child_output = importlib.import_module(f"{IMPORT_SERVICE_OUTPUT}.child")
    child_request_message_type = child_output.ChildRequestMessage
    nested_request_message_type = output.NestedRequestMessage
    request_message_type = output.RequestMessage
    request_response_type = output.RequestResponse
    test_base_type = output.TestBase
    test_stub_type = output.TestStub

    class Service(test_base_type):
        async def do_thing(self, message):
            return request_response_type(value=message.argument)

        async def do_thing_2(self, message):
            return request_response_type(value=message.child_argument)

        async def do_thing_3(self, message):
            return request_response_type(value=message.nested_argument)

    async with grpcio_channel_for_service(Service()) as channel:
        client = test_stub_type(channel)
        response = await client.do_thing(request_message_type(argument=11))
        child_response = await client.do_thing_2(child_request_message_type(child_argument=22))
        nested_response = await client.do_thing_3(nested_request_message_type(nested_argument=33))

    assert response.value == 11
    assert child_response.value == 22
    assert nested_response.value == 33


@pytest.mark.asyncio
async def test_generated_grpcio_async_separate_package_imports_round_trip(requires_grpcio) -> None:
    messages = importlib.import_module(f"{SEPARATE_PACKAGE_OUTPUT}.messages")
    service = importlib.import_module(f"{SEPARATE_PACKAGE_OUTPUT}.service")
    test_base_type = service.TestBase
    test_stub_type = service.TestStub

    class Service(test_base_type):
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

    async with grpcio_channel_for_service(Service()) as channel:
        client = test_stub_type(channel)
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

    from tests.outputs.deprecated_client_async_transport_grpcio.deprecated import (
        Empty as empty_type,
        TestServiceStub as test_service_stub_type,
    )

    async def deprecated_func(request, context):
        return empty_type()

    handler = grpc.method_handlers_generic_handler(
        "deprecated.TestService",
        {
            "deprecated_func": grpc.unary_unary_rpc_method_handler(
                deprecated_func,
                request_deserializer=empty_type.FromString,
                response_serializer=empty_type.SerializeToString,
            )
        },
    )

    async with grpcio_channel_for_handler(handler) as channel:
        with pytest.warns(DeprecationWarning) as warnings:
            response = await test_service_stub_type(channel).deprecated_func()

    assert response == empty_type()
    assert len(warnings) == 1
