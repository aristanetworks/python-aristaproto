#!/usr/bin/env python

import os
import sys

from aristaproto.lib.google.protobuf.compiler import (
    CodeGeneratorRequest,
)
from aristaproto.plugin.models import monkey_patch_oneof_index
from aristaproto.plugin.parser import generate_code


def main() -> None:
    """The plugin's main entry point."""
    # Read request message from stdin
    data = sys.stdin.buffer.read()

    # Apply Work around for proto2/3 difference in protoc messages
    monkey_patch_oneof_index()

    # Parse request
    request = CodeGeneratorRequest()
    request.parse(data)

    dump_file = os.getenv("ARISTAPROTO_DUMP")
    if dump_file:
        dump_request(dump_file, request)

    # Generate code
    response = generate_code(request)

    # Serialise response message
    output = response.SerializeToString()

    # Write to stdout
    sys.stdout.buffer.write(output)


def dump_request(dump_file: str, request: CodeGeneratorRequest) -> None:
    """
    For developers: Supports running plugin.py standalone so its possible to debug it.
    Run protoc (or generate.py) with ARISTAPROTO_DUMP="yourfile.bin" to write the request to a file.
    Then run plugin.py from your IDE in debugging mode, and redirect stdin to the file.
    """
    with open(str(dump_file), "wb") as fh:
        sys.stderr.write(f"\033[31mWriting input from protoc to: {dump_file}\033[0m\n")
        fh.write(request.SerializeToString())


if __name__ == "__main__":
    main()
