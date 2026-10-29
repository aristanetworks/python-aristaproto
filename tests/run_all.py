"""Run the locked generation and test toolchain in isolated Python environments."""

import argparse
import os
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory


PYTHON_VERSIONS = ("3.15", "3.14", "3.13", "3.12", "3.11", "3.10")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "versions", nargs="*", help="Python versions to test (default: 3.10–3.15)"
    )
    versions = parser.parse_args().versions or PYTHON_VERSIONS
    project = Path(__file__).resolve().parent.parent
    environment = os.environ.copy()
    environment.pop("VIRTUAL_ENV", None)

    with TemporaryDirectory(prefix="aristaproto-tests-") as directory:
        for index, version in enumerate(versions):
            print(f"Testing Python {version}", flush=True)
            environment["UV_PYTHON"] = version
            environment["UV_PROJECT_ENVIRONMENT"] = str(Path(directory) / str(index))
            subprocess.run(
                [
                    "uv",
                    "sync",
                    "--locked",
                    "--no-default-groups",
                    "--group",
                    "compiler",
                    "--group",
                    "test",
                    "--extra",
                    "compiler",
                    "--no-build",
                ],
                cwd=project,
                env=environment,
                check=True,
            )
            for module, arguments in (
                ("tests.generate", []),
                ("pytest", ["tests/", "--cov", "aristaproto"]),
            ):
                subprocess.run(
                    [
                        "uv",
                        "run",
                        "--no-sync",
                        "--no-default-groups",
                        "python",
                        "-m",
                        module,
                        *arguments,
                    ],
                    cwd=project,
                    env=environment,
                    check=True,
                )


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as error:
        raise SystemExit(error.returncode) from error
