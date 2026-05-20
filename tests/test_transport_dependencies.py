import os
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Iterable

import pytest

from tests.util import inputs_path, protoc


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"


def run_with_blocked_transports(
    code: str,
    *,
    blocked: Iterable[str],
    pythonpath: Iterable[Path] = (),
) -> subprocess.CompletedProcess[str]:
    blocked_imports = f"""
import importlib.abc
import sys


class BlockTransportImports(importlib.abc.MetaPathFinder):
    blocked = {set(blocked)!r}

    def find_spec(self, fullname, path=None, target=None):
        root_name = fullname.split(".", 1)[0]
        if root_name in self.blocked:
            raise ModuleNotFoundError(
                f"No module named {{root_name!r}}",
                name=root_name,
            )
        return None


sys.meta_path.insert(0, BlockTransportImports())
"""
    env = os.environ.copy()
    extra_pythonpath = [
        *(str(path) for path in pythonpath),
        str(SRC),
        str(ROOT),
    ]
    if env.get("PYTHONPATH"):
        extra_pythonpath.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(extra_pythonpath)

    return subprocess.run(
        [sys.executable, "-c", textwrap.dedent(blocked_imports + code)],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_import_aristaproto_does_not_require_transport_extras() -> None:
    result = run_with_blocked_transports(
        "import aristaproto\nprint(aristaproto.Message.__name__)",
        blocked={"grpc", "grpclib"},
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "Message"


def test_generated_message_only_module_does_not_require_transport_extras() -> None:
    result = run_with_blocked_transports(
        "from tests.output_aristaproto.bool import Test\nprint(Test(value=True).value)",
        blocked={"grpc", "grpclib"},
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "True"


@pytest.mark.parametrize(
    ("module_name", "blocked", "extra"),
    [
        ("aristaproto.grpcio_client", "grpc", "aristaproto[grpcio]"),
        ("aristaproto.grpcio_server", "grpc", "aristaproto[grpcio]"),
        ("aristaproto.grpc.grpclib_client", "grpclib", "aristaproto[grpclib]"),
        ("aristaproto.grpc.grpclib_server", "grpclib", "aristaproto[grpclib]"),
    ],
)
def test_transport_runtime_modules_report_missing_extra(
    module_name: str,
    blocked: str,
    extra: str,
) -> None:
    result = run_with_blocked_transports(
        f"import {module_name}",
        blocked={blocked},
    )

    assert result.returncode != 0
    assert extra in result.stderr


@pytest.mark.asyncio
async def test_generated_default_grpcio_service_module_reports_missing_extra(
    tmp_path,
) -> None:
    stdout, stderr, returncode = await protoc(inputs_path.joinpath("service"), tmp_path)

    assert returncode == 0, (
        f"protoc failed\nstdout:\n{stdout.decode()}\nstderr:\n{stderr.decode()}"
    )

    result = run_with_blocked_transports(
        "import service",
        blocked={"grpc"},
        pythonpath=(tmp_path,),
    )

    assert result.returncode != 0
    assert "aristaproto[grpcio]" in result.stderr


@pytest.mark.asyncio
async def test_generated_grpclib_service_module_reports_missing_extra(tmp_path) -> None:
    stdout, stderr, returncode = await protoc(
        inputs_path.joinpath("service"),
        tmp_path,
        plugin_options=("transport=grpclib",),
    )

    assert returncode == 0, (
        f"protoc failed\nstdout:\n{stdout.decode()}\nstderr:\n{stderr.decode()}"
    )

    result = run_with_blocked_transports(
        "import service",
        blocked={"grpclib"},
        pythonpath=(tmp_path,),
    )

    assert result.returncode != 0
    assert "aristaproto[grpclib]" in result.stderr
