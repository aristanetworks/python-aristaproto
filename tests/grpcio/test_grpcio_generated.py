import importlib
import inspect
import sys
import warnings
from pathlib import Path
from types import ModuleType
from typing import (
    AsyncIterator,
)

import grpc
import pytest
import pytest_asyncio

from aristaproto.grpc.grpclib_client import ServiceStub as GrpclibServiceStub
from aristaproto.grpc.grpclib_server import ServiceBase as GrpclibServiceBase
from aristaproto.grpcio_client import ServiceStub as GrpcioServiceStub
from aristaproto.grpcio_server import ServiceBase as GrpcioServiceBase
from tests.inputs import config as test_input_config
from tests.util import (
    find_module,
    inputs_path,
    protoc,
)


GRPCIO_GENERATED_PACKAGE = "tests.output_aristaproto"
GRPCIO_SERVICE_TEST_CASES = sorted(
    test_input_config.services | {"deprecated", "documentation"}
)


def generated_service_classes(
    module: ModuleType,
) -> list[tuple[type[GrpcioServiceStub], type[GrpcioServiceBase]]]:
    classes = []
    for name, stub_class in vars(module).items():
        if (
            not inspect.isclass(stub_class)
            or stub_class.__module__ != module.__name__
            or not name.endswith("Stub")
        ):
            continue

        base_class = getattr(module, f"{name.removesuffix('Stub')}Base", None)
        if inspect.isclass(base_class) and base_class.__module__ == module.__name__:
            classes.append((stub_class, base_class))
    return classes


def has_generated_service_classes(module: ModuleType) -> bool:
    return bool(generated_service_classes(module))


@pytest_asyncio.fixture
async def generated_service_module(tmp_path, reset_sys_path):
    stdout, stderr, returncode = await protoc(
        inputs_path.joinpath("service"),
        tmp_path,
    )

    assert returncode == 0, (
        f"protoc failed\nstdout:\n{stdout.decode()}\nstderr:\n{stderr.decode()}"
    )

    sys.path.insert(0, str(tmp_path))
    sys.modules.pop("service", None)
    try:
        yield (
            importlib.import_module("service"),
            tmp_path.joinpath("service", "__init__.py").read_text(),
        )
    finally:
        sys.modules.pop("service", None)


def test_generated_grpcio_code_shape(
    generated_service_module: tuple[ModuleType, str],
) -> None:
    module, source = generated_service_module

    assert "from aristaproto.grpcio_client import" in source
    assert "from aristaproto.grpcio_server import ServiceBase" in source
    assert "import grpc" in source
    assert "grpclib" not in source
    assert "class TestStub(ServiceStub):" in source
    assert "class TestBase(ServiceBase):" in source
    assert "def _grpcio_rpc_handler(self) -> grpc.GenericRpcHandler:" in source
    assert "__mapping__" not in source
    assert "deadline" not in inspect.signature(module.TestStub.do_thing).parameters
    assert set(inspect.signature(module.TestStub.do_thing).parameters) == {
        "self",
        "do_thing_request",
        "timeout",
        "metadata",
        "credentials",
        "wait_for_ready",
    }
    assert issubclass(module.TestStub, GrpcioServiceStub)
    assert issubclass(module.TestBase, GrpcioServiceBase)


@pytest.mark.asyncio
async def test_generated_grpclib_transport_option_keeps_legacy_shape(
    tmp_path,
    reset_sys_path,
) -> None:
    stdout, stderr, returncode = await protoc(
        inputs_path.joinpath("service"),
        tmp_path,
        plugin_options=("transport=grpclib",),
    )

    assert returncode == 0, (
        f"protoc failed\nstdout:\n{stdout.decode()}\nstderr:\n{stderr.decode()}"
    )

    sys.path.insert(0, str(tmp_path))
    sys.modules.pop("service", None)
    try:
        module = importlib.import_module("service")
        source = tmp_path.joinpath("service", "__init__.py").read_text()
    finally:
        sys.modules.pop("service", None)

    assert "from aristaproto.grpc.grpclib_client import ServiceStub" in source
    assert "from aristaproto.grpc.grpclib_server import ServiceBase" in source
    assert "import grpclib" in source
    assert "grpcio" not in source
    assert "class TestStub(ServiceStub):" in source
    assert "class TestBase(ServiceBase):" in source
    assert "__mapping__" in source
    assert "deadline" in inspect.signature(module.TestStub.do_thing).parameters
    assert issubclass(module.TestStub, GrpclibServiceStub)
    assert issubclass(module.TestBase, GrpclibServiceBase)


@pytest.mark.parametrize("test_case_name", GRPCIO_SERVICE_TEST_CASES)
def test_generated_grpcio_service_contract_across_existing_service_specs(
    test_case_name: str,
) -> None:
    root_module = importlib.import_module(
        f"{GRPCIO_GENERATED_PACKAGE}.{test_case_name}"
    )
    service_module = find_module(root_module, has_generated_service_classes)

    assert service_module is not None
    source = Path(service_module.__file__).read_text()
    assert "from aristaproto.grpcio_client import" in source
    assert "from aristaproto.grpcio_server import ServiceBase" in source
    assert "import grpc" in source
    assert "grpclib" not in source
    assert "__mapping__" not in source
    assert "deadline" not in source

    for stub_class, base_class in generated_service_classes(service_module):
        assert issubclass(stub_class, GrpcioServiceStub)
        assert issubclass(base_class, GrpcioServiceBase)
        assert hasattr(base_class(), "_grpcio_rpc_handler")


def test_generated_grpcio_service_separate_packages_import_shape() -> None:
    service_module = importlib.import_module(
        f"{GRPCIO_GENERATED_PACKAGE}.service_separate_packages.things.service"
    )
    messages_module = importlib.import_module(
        f"{GRPCIO_GENERATED_PACKAGE}.service_separate_packages.things.messages"
    )
    source = Path(service_module.__file__).read_text()
    messages_source = Path(messages_module.__file__).read_text()

    assert service_module.__all__ == ("TestStub", "TestBase")
    assert "from .. import messages as _messages__" in source
    assert "AsyncIterable" in source
    assert "AsyncIterator" in source
    assert "Iterable" in source
    assert "Union" in source
    assert inspect.signature(service_module.TestStub.do_many_things).parameters[
        "messages_do_thing_request_iterator"
    ].annotation == (
        "Union[AsyncIterable[_messages__.DoThingRequest], "
        "Iterable[_messages__.DoThingRequest]]"
    )
    assert "comments: List[str]" in messages_source


@pytest.mark.asyncio
async def test_generated_grpcio_deprecated_method_warns() -> None:
    module = importlib.import_module(f"{GRPCIO_GENERATED_PACKAGE}.deprecated")
    stub = module.TestServiceStub(object())

    async def fake_unary_unary(_route, _request, response_type, **_kwargs):
        return response_type()

    stub._unary_unary = fake_unary_unary

    with pytest.warns(DeprecationWarning) as record:
        await stub.deprecated_func(module.Empty())

    assert len(record) == 1
    assert str(record[0].message) == "TestService.deprecated_func is deprecated"

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        await stub.func(module.Empty())


async def async_get_thing_requests(
    module: ModuleType,
    names: list[str],
) -> AsyncIterator:
    for name in names:
        yield module.GetThingRequest(name=name)


@pytest_asyncio.fixture
async def generated_grpcio_service(generated_service_module):
    module, _source = generated_service_module

    class RecordingGeneratedService(module.TestBase):
        async def do_thing(self, do_thing_request):
            return module.DoThingResponse(names=[do_thing_request.name])

        async def do_many_things(self, do_thing_request_iterator):
            return module.DoThingResponse(
                names=[
                    do_thing_request.name
                    async for do_thing_request in do_thing_request_iterator
                ]
            )

        async def get_thing_versions(self, get_thing_request):
            for version in range(1, 4):
                yield module.GetThingResponse(
                    name=get_thing_request.name,
                    version=version,
                )

        async def get_different_things(self, get_thing_request_iterator):
            version = 0
            async for get_thing_request in get_thing_request_iterator:
                version += 1
                yield module.GetThingResponse(
                    name=get_thing_request.name,
                    version=version,
                )

    service = RecordingGeneratedService()
    server = grpc.aio.server()
    server.add_generic_rpc_handlers((service._grpcio_rpc_handler(),))
    port = server.add_insecure_port("127.0.0.1:0")
    await server.start()
    channel = grpc.aio.insecure_channel(f"127.0.0.1:{port}")
    try:
        yield module.TestStub(channel), module
    finally:
        await channel.close()
        await server.stop(grace=None)


@pytest.mark.asyncio
async def test_generated_grpcio_stubs_and_bases_support_all_cardinalities(
    generated_grpcio_service,
) -> None:
    client, module = generated_grpcio_service

    response = await client.do_thing(module.DoThingRequest(name="clean room"))
    assert response == module.DoThingResponse(names=["clean room"])

    unary_stream_responses = [
        response
        async for response in client.get_thing_versions(
            module.GetThingRequest(name="switch")
        )
    ]
    assert unary_stream_responses == [
        module.GetThingResponse(name="switch", version=1),
        module.GetThingResponse(name="switch", version=2),
        module.GetThingResponse(name="switch", version=3),
    ]

    stream_unary_response = await client.do_many_things(
        [
            module.DoThingRequest(name="one"),
            module.DoThingRequest(name="two"),
        ]
    )
    assert stream_unary_response == module.DoThingResponse(names=["one", "two"])

    stream_stream_responses = [
        response
        async for response in client.get_different_things(
            async_get_thing_requests(module, ["leaf", "spine"])
        )
    ]
    assert stream_stream_responses == [
        module.GetThingResponse(name="leaf", version=1),
        module.GetThingResponse(name="spine", version=2),
    ]


@pytest.mark.asyncio
async def test_generated_grpcio_base_unimplemented_methods_raise_grpcio_status(
    generated_service_module,
) -> None:
    module, _source = generated_service_module
    service = module.TestBase()
    server = grpc.aio.server()
    server.add_generic_rpc_handlers((service._grpcio_rpc_handler(),))
    port = server.add_insecure_port("127.0.0.1:0")
    await server.start()
    channel = grpc.aio.insecure_channel(f"127.0.0.1:{port}")
    try:
        client = module.TestStub(channel)
        with pytest.raises(grpc.aio.AioRpcError) as error:
            await client.do_thing(module.DoThingRequest(name="missing"))

        assert error.value.code() == grpc.StatusCode.UNIMPLEMENTED
    finally:
        await channel.close()
        await server.stop(grace=None)


@pytest.mark.asyncio
async def test_generated_grpcio_separate_package_service_round_trip() -> None:
    service_module = importlib.import_module(
        f"{GRPCIO_GENERATED_PACKAGE}.service_separate_packages.things.service"
    )
    messages_module = importlib.import_module(
        f"{GRPCIO_GENERATED_PACKAGE}.service_separate_packages.things.messages"
    )

    class SeparatePackageService(service_module.TestBase):
        async def do_thing(self, messages_do_thing_request):
            return messages_module.DoThingResponse(
                names=[messages_do_thing_request.name]
            )

        async def do_many_things(self, messages_do_thing_request_iterator):
            return messages_module.DoThingResponse(
                names=[
                    request.name async for request in messages_do_thing_request_iterator
                ]
            )

        async def get_thing_versions(self, messages_get_thing_request):
            for version in range(1, 3):
                yield messages_module.GetThingResponse(
                    name=messages_get_thing_request.name,
                    version=version,
                )

        async def get_different_things(self, messages_get_thing_request_iterator):
            version = 0
            async for request in messages_get_thing_request_iterator:
                version += 1
                yield messages_module.GetThingResponse(
                    name=request.name,
                    version=version,
                )

    service = SeparatePackageService()
    server = grpc.aio.server()
    server.add_generic_rpc_handlers((service._grpcio_rpc_handler(),))
    port = server.add_insecure_port("127.0.0.1:0")
    await server.start()
    channel = grpc.aio.insecure_channel(f"127.0.0.1:{port}")
    try:
        client = service_module.TestStub(channel)

        assert await client.do_thing(
            messages_module.DoThingRequest(name="leaf")
        ) == messages_module.DoThingResponse(names=["leaf"])
        assert await client.do_many_things(
            [
                messages_module.DoThingRequest(name="one"),
                messages_module.DoThingRequest(name="two"),
            ]
        ) == messages_module.DoThingResponse(names=["one", "two"])
        assert [
            response
            async for response in client.get_thing_versions(
                messages_module.GetThingRequest(name="spine")
            )
        ] == [
            messages_module.GetThingResponse(name="spine", version=1),
            messages_module.GetThingResponse(name="spine", version=2),
        ]
        assert [
            response
            async for response in client.get_different_things(
                [
                    messages_module.GetThingRequest(name="left"),
                    messages_module.GetThingRequest(name="right"),
                ]
            )
        ] == [
            messages_module.GetThingResponse(name="left", version=1),
            messages_module.GetThingResponse(name="right", version=2),
        ]
    finally:
        await channel.close()
        await server.stop(grace=None)


@pytest.mark.asyncio
async def test_generated_grpcio_imported_service_input_messages_round_trip() -> None:
    module = importlib.import_module(
        f"{GRPCIO_GENERATED_PACKAGE}.import_service_input_message"
    )
    child_module = importlib.import_module(
        f"{GRPCIO_GENERATED_PACKAGE}.import_service_input_message.child"
    )

    class ImportedInputService(module.TestBase):
        async def do_thing(self, request_message):
            return module.RequestResponse(value=request_message.argument)

        async def do_thing2(self, child_child_request_message):
            return module.RequestResponse(
                value=child_child_request_message.child_argument
            )

        async def do_thing3(self, nested_request_message):
            return module.RequestResponse(value=nested_request_message.nested_argument)

    service = ImportedInputService()
    server = grpc.aio.server()
    server.add_generic_rpc_handlers((service._grpcio_rpc_handler(),))
    port = server.add_insecure_port("127.0.0.1:0")
    await server.start()
    channel = grpc.aio.insecure_channel(f"127.0.0.1:{port}")
    try:
        client = module.TestStub(channel)

        assert await client.do_thing(
            module.RequestMessage(argument=1)
        ) == module.RequestResponse(value=1)
        assert await client.do_thing2(
            child_module.ChildRequestMessage(child_argument=2)
        ) == module.RequestResponse(value=2)
        assert await client.do_thing3(
            module.NestedRequestMessage(nested_argument=3)
        ) == module.RequestResponse(value=3)
    finally:
        await channel.close()
        await server.stop(grace=None)
