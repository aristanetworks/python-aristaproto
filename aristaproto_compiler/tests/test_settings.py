import pytest

from aristaproto_compiler.lib.google.protobuf import FileDescriptorProto, MethodDescriptorProto, ServiceDescriptorProto
from aristaproto_compiler.lib.google.protobuf.compiler import CodeGeneratorRequest
from aristaproto_compiler.plugin.models import (
    OutputTemplate,
    PluginRequestCompiler,
    ServiceCompiler,
    ServiceMethodCompiler,
)
from aristaproto_compiler.plugin.parser import get_settings
from aristaproto_compiler.settings import (
    ClientAsyncTransport,
    ClientGeneration,
    ServerAsyncTransport,
    ServerGeneration,
)


def test_transport_defaults_preserve_existing_async_grpclib_behavior():
    settings = get_settings([])

    assert settings.client_generation is ClientGeneration.SYNC
    assert settings.client_async_transport is ClientAsyncTransport.GRPCLIB
    assert settings.server_generation is ServerGeneration.NONE
    assert settings.server_async_transport is ServerAsyncTransport.GRPCLIB


def test_async_generation_defaults_to_grpclib_transports():
    settings = get_settings(["client_generation=async", "server_generation=async"])

    assert settings.client_generation is ClientGeneration.ASYNC
    assert settings.client_async_transport is ClientAsyncTransport.GRPCLIB
    assert settings.server_generation is ServerGeneration.ASYNC
    assert settings.server_async_transport is ServerAsyncTransport.GRPCLIB


def test_client_async_transport_can_select_grpcio_when_async_client_is_generated():
    settings = get_settings(["client_generation=async", "client_async_transport=grpcio"])

    assert settings.client_generation is ClientGeneration.ASYNC
    assert settings.client_async_transport is ClientAsyncTransport.GRPCIO


def test_client_async_transport_can_select_grpcio_when_sync_and_async_clients_are_generated():
    settings = get_settings(["client_generation=sync_async", "client_async_transport=grpcio"])

    assert settings.client_generation is ClientGeneration.SYNC_ASYNC
    assert settings.client_async_transport is ClientAsyncTransport.GRPCIO


def test_server_async_transport_can_select_grpcio_when_async_server_is_generated():
    settings = get_settings(["server_generation=async", "server_async_transport=grpcio"])

    assert settings.server_generation is ServerGeneration.ASYNC
    assert settings.server_async_transport is ServerAsyncTransport.GRPCIO


@pytest.mark.parametrize(
    ("option", "expected_error"),
    [
        ("client_async_transport=unknown", "Invalid client_async_transport option: unknown"),
        ("server_async_transport=unknown", "Invalid server_async_transport option: unknown"),
    ],
)
def test_invalid_transport_values_raise_explicit_errors(option: str, expected_error: str):
    with pytest.raises(ValueError, match=expected_error):
        get_settings([option])


def test_grpcio_service_and_method_names_include_package_when_present():
    settings = get_settings([])
    request = PluginRequestCompiler(plugin_request_obj=CodeGeneratorRequest())
    output = OutputTemplate(
        parent_request=request,
        package_proto_obj=FileDescriptorProto(package="example.v1"),
        settings=settings,
    )
    service = ServiceCompiler(
        source_file=FileDescriptorProto(package="example.v1"),
        output_file=output,
        proto_obj=ServiceDescriptorProto(name="ThingService"),
        path=[6, 0],
    )
    method = ServiceMethodCompiler(
        source_file=FileDescriptorProto(package="example.v1"),
        parent=service,
        proto_obj=MethodDescriptorProto(name="DoThing"),
        path=[6, 0, 2, 0],
    )

    assert service.grpcio_service_name == "example.v1.ThingService"
    assert method.grpcio_method_name == "example.v1.ThingService.DoThing"


def test_grpcio_service_and_method_names_omit_package_when_absent():
    settings = get_settings([])
    request = PluginRequestCompiler(plugin_request_obj=CodeGeneratorRequest())
    output = OutputTemplate(
        parent_request=request,
        package_proto_obj=FileDescriptorProto(),
        settings=settings,
    )
    service = ServiceCompiler(
        source_file=FileDescriptorProto(),
        output_file=output,
        proto_obj=ServiceDescriptorProto(name="ThingService"),
        path=[6, 0],
    )
    method = ServiceMethodCompiler(
        source_file=FileDescriptorProto(),
        parent=service,
        proto_obj=MethodDescriptorProto(name="DoThing"),
        path=[6, 0, 2, 0],
    )

    assert service.grpcio_service_name == "ThingService"
    assert method.grpcio_method_name == "ThingService.DoThing"
