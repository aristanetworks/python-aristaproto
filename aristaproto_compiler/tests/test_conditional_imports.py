import asyncio
import importlib
import importlib.abc
import sys
import types
from collections.abc import Iterator
from contextlib import contextmanager, nullcontext
from pathlib import Path

import pytest

from tests.util import protoc

RUNTIME_SRC = Path(__file__).resolve().parents[2] / "aristaproto" / "src"


class BlockedImportFinder(importlib.abc.MetaPathFinder):
    def __init__(self, *blocked_modules: str) -> None:
        self.blocked_modules = blocked_modules

    def find_spec(self, fullname: str, path: object, target: object = None) -> None:
        if any(fullname == blocked or fullname.startswith(f"{blocked}.") for blocked in self.blocked_modules):
            raise ModuleNotFoundError(f"No module named {fullname!r}")
        return None


@contextmanager
def block_imports(*module_names: str) -> Iterator[None]:
    saved_modules = {
        name: module
        for name, module in list(sys.modules.items())
        if any(name == blocked or name.startswith(f"{blocked}.") for blocked in module_names)
    }
    for name in saved_modules:
        del sys.modules[name]

    blocked_aristaproto_attributes: dict[str, object] = {}
    missing_aristaproto_attributes: set[str] = set()
    aristaproto_module = sys.modules.get("aristaproto")
    if aristaproto_module is not None:
        for name in module_names:
            if name.startswith("aristaproto.") and name.count(".") == 1:
                attribute = name.rsplit(".", 1)[1]
                if hasattr(aristaproto_module, attribute):
                    blocked_aristaproto_attributes[attribute] = getattr(aristaproto_module, attribute)
                    delattr(aristaproto_module, attribute)
                else:
                    missing_aristaproto_attributes.add(attribute)

    finder = BlockedImportFinder(*module_names)
    sys.meta_path.insert(0, finder)
    try:
        yield
    finally:
        sys.meta_path.remove(finder)
        for name in list(sys.modules):
            if any(name == blocked or name.startswith(f"{blocked}.") for blocked in module_names):
                del sys.modules[name]
        sys.modules.update(saved_modules)
        if aristaproto_module is not None:
            for attribute in missing_aristaproto_attributes:
                if hasattr(aristaproto_module, attribute):
                    delattr(aristaproto_module, attribute)
            for attribute, value in blocked_aristaproto_attributes.items():
                setattr(aristaproto_module, attribute, value)


@contextmanager
def generated_import_path(output_dir: Path) -> Iterator[None]:
    paths = [output_dir.parent.as_posix()]
    if RUNTIME_SRC.is_dir():
        paths.insert(0, RUNTIME_SRC.as_posix())

    sys.path[:0] = paths
    try:
        yield
    finally:
        del sys.path[: len(paths)]


@contextmanager
def stub_transport_runtime(*module_names: str) -> Iterator[None]:
    import aristaproto

    class ServiceStub:
        pass

    class ServiceBase:
        pass

    grpc = types.ModuleType("grpc")
    grpc.CallCredentials = type("CallCredentials", (), {})
    grpc.Channel = type("Channel", (), {})
    grpc.GenericRpcHandler = type("GenericRpcHandler", (), {})

    grpclib = types.ModuleType("grpclib")
    grpclib.const = types.SimpleNamespace(Status=types.SimpleNamespace(UNIMPLEMENTED=object()))
    grpclib.GRPCError = type("GRPCError", (Exception,), {})

    aristaproto_grpcio = types.ModuleType("aristaproto.grpcio")
    aristaproto_grpcio.ServiceStub = ServiceStub
    aristaproto_grpcio.ServiceBase = ServiceBase

    aristaproto_grpclib = types.ModuleType("aristaproto.grpclib")
    aristaproto_grpclib.ServiceStub = ServiceStub
    aristaproto_grpclib.ServiceBase = ServiceBase

    available_stubs = {
        "grpc": grpc,
        "grpclib": grpclib,
        "aristaproto.grpcio": aristaproto_grpcio,
        "aristaproto.grpclib": aristaproto_grpclib,
    }
    stubs = {name: available_stubs[name] for name in module_names}
    previous_modules = {name: sys.modules.get(name) for name in stubs}
    previous_attributes = {
        "grpcio": getattr(aristaproto, "grpcio", None),
        "grpclib": getattr(aristaproto, "grpclib", None),
    }
    had_attributes = {
        "grpcio": hasattr(aristaproto, "grpcio"),
        "grpclib": hasattr(aristaproto, "grpclib"),
    }

    sys.modules.update(stubs)
    if "aristaproto.grpcio" in stubs:
        aristaproto.grpcio = aristaproto_grpcio
    if "aristaproto.grpclib" in stubs:
        aristaproto.grpclib = aristaproto_grpclib
    try:
        yield
    finally:
        for name, module in previous_modules.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module
        for name, value in previous_attributes.items():
            if had_attributes[name]:
                setattr(aristaproto, name, value)
            elif hasattr(aristaproto, name):
                delattr(aristaproto, name)


def import_generated_module(
    output_dir: Path,
    module_name: str,
    blocked_modules: tuple[str, ...],
    *,
    stub_modules: tuple[str, ...] = (),
) -> None:
    for name in list(sys.modules):
        if name == module_name.split(".")[0] or name.startswith(f"{module_name.split('.')[0]}."):
            del sys.modules[name]

    stubs = stub_transport_runtime(*stub_modules) if stub_modules else nullcontext()
    with generated_import_path(output_dir), stubs, block_imports(*blocked_modules):
        importlib.import_module(module_name)


async def generate_fixture(
    tmp_path: Path,
    fixture_name: str,
    *,
    client_generation: str,
    server_generation: str,
    client_async_transport: str | None = None,
    server_async_transport: str | None = None,
) -> Path:
    output_dir = tmp_path / fixture_name
    output_dir.mkdir()
    input_dir = Path(__file__).parent / "inputs" / fixture_name

    stdout, stderr, returncode = await protoc(
        input_dir,
        output_dir,
        client_generation=client_generation,
        server_generation=server_generation,
        client_async_transport=client_async_transport,
        server_async_transport=server_async_transport,
    )

    assert returncode == 0, (stdout.decode(), stderr.decode())
    return output_dir


@pytest.mark.parametrize(
    (
        "fixture_name",
        "module_name",
        "client_generation",
        "server_generation",
        "client_async_transport",
        "server_async_transport",
        "blocked_modules",
        "stub_modules",
    ),
    [
        (
            "bool",
            "bool.bool",
            "none",
            "none",
            None,
            None,
            ("grpc", "grpclib", "aristaproto.grpcio", "aristaproto.grpclib"),
            (),
        ),
        ("service", "service.service", "sync", "none", None, None, ("grpclib", "aristaproto.grpclib"), ("grpc",)),
        (
            "service",
            "service.service",
            "async",
            "none",
            None,
            None,
            ("grpc", "aristaproto.grpcio"),
            ("grpclib", "aristaproto.grpclib"),
        ),
        (
            "service",
            "service.service",
            "async",
            "none",
            "grpcio",
            None,
            ("grpclib", "aristaproto.grpclib"),
            ("grpc", "aristaproto.grpcio"),
        ),
        (
            "service",
            "service.service",
            "none",
            "async",
            None,
            None,
            ("grpc", "aristaproto.grpcio"),
            ("grpclib", "aristaproto.grpclib"),
        ),
        (
            "service",
            "service.service",
            "none",
            "async",
            None,
            "grpcio",
            ("grpclib", "aristaproto.grpclib"),
            ("grpc", "aristaproto.grpcio"),
        ),
    ],
)
def test_generated_modules_import_without_unselected_transport_extras(
    tmp_path: Path,
    fixture_name: str,
    module_name: str,
    client_generation: str,
    server_generation: str,
    client_async_transport: str | None,
    server_async_transport: str | None,
    blocked_modules: tuple[str, ...],
    stub_modules: tuple[str, ...],
) -> None:
    output_dir = asyncio.run(
        generate_fixture(
            tmp_path,
            fixture_name,
            client_generation=client_generation,
            server_generation=server_generation,
            client_async_transport=client_async_transport,
            server_async_transport=server_async_transport,
        )
    )

    import_generated_module(output_dir, module_name, blocked_modules, stub_modules=stub_modules)


@pytest.mark.parametrize(
    (
        "client_generation",
        "server_generation",
        "client_async_transport",
        "server_async_transport",
        "blocked_modules",
    ),
    [
        ("sync", "none", None, None, ("grpc",)),
        ("async", "none", None, None, ("grpclib", "aristaproto.grpclib")),
        ("async", "none", "grpcio", None, ("grpc", "aristaproto.grpcio")),
        ("none", "async", None, None, ("grpclib", "aristaproto.grpclib")),
        ("none", "async", None, "grpcio", ("grpc", "aristaproto.grpcio")),
    ],
)
def test_generated_modules_require_selected_transport_extra(
    tmp_path: Path,
    client_generation: str,
    server_generation: str,
    client_async_transport: str | None,
    server_async_transport: str | None,
    blocked_modules: tuple[str, ...],
) -> None:
    output_dir = asyncio.run(
        generate_fixture(
            tmp_path,
            "service",
            client_generation=client_generation,
            server_generation=server_generation,
            client_async_transport=client_async_transport,
            server_async_transport=server_async_transport,
        )
    )

    with pytest.raises(ModuleNotFoundError):
        import_generated_module(output_dir, "service.service", blocked_modules)
