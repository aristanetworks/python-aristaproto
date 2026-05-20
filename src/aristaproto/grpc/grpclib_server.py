from abc import ABC
from collections.abc import AsyncIterable
from typing import (
    Any,
    Callable,
)


try:
    import grpclib
    import grpclib.server
except ModuleNotFoundError as exc:
    if exc.name != "grpclib":
        raise
    raise ModuleNotFoundError(
        "grpclib transport support requires the grpclib extra. "
        'Install it with `pip install "aristaproto[grpclib]"`.'
    ) from exc


class ServiceBase(ABC):
    """
    Base class for async gRPC servers.
    """

    async def _call_rpc_handler_server_stream(
        self,
        handler: Callable,
        stream: grpclib.server.Stream,
        request: Any,
    ) -> None:
        response_iter = handler(request)
        # check if response is actually an AsyncIterator
        # this might be false if the method just returns without
        # yielding at least once
        # in that case, we just interpret it as an empty iterator
        if isinstance(response_iter, AsyncIterable):
            async for response_message in response_iter:
                await stream.send_message(response_message)
        else:
            response_iter.close()
