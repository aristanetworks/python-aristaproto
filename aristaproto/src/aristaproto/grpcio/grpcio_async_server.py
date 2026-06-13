from __future__ import annotations

import inspect
from abc import ABC
from collections.abc import AsyncIterable, AsyncIterator, Awaitable, Callable
from contextvars import ContextVar
from typing import TYPE_CHECKING, NoReturn

import grpc

if TYPE_CHECKING:
    import grpc.aio

    from aristaproto._types import IProtoMessage, T

ServerStreamingResponse = AsyncIterable["IProtoMessage"] | Awaitable[None] | None
SERVER_STREAMING_RETURN_ERROR = (
    "Server-streaming RPC handlers must return an AsyncIterable or None; "
    "async def handlers must not return response values"
)


class ServiceBase(ABC):
    """
    Base class for async grpcio servers.
    """

    __grpcio_context: ContextVar[grpc.aio.ServicerContext | None] = ContextVar(
        "aristaproto_grpcio_context",
        default=None,
    )

    @property
    def _grpcio_context(self) -> grpc.aio.ServicerContext:
        context = self.__grpcio_context.get()
        if context is None:
            raise RuntimeError("_grpcio_context is only available while handling a grpcio request")
        return context

    async def _grpcio_unimplemented(self) -> NoReturn:
        await self._grpcio_context.abort(grpc.StatusCode.UNIMPLEMENTED, "")

    def _grpcio_generic_rpc_handler(
        self,
        service_name: str,
        method_handlers: dict[str, grpc.RpcMethodHandler],
    ) -> grpc.GenericRpcHandler:
        return grpc.method_handlers_generic_handler(service_name, method_handlers)

    def _grpcio_unary_unary_rpc_method_handler(
        self,
        handler: Callable[[IProtoMessage], Awaitable[T]],
        request_type: type[IProtoMessage],
        response_type: type[IProtoMessage],
    ) -> grpc.RpcMethodHandler:
        async def rpc_handler(request: IProtoMessage, context: grpc.aio.ServicerContext) -> T:
            token = self.__grpcio_context.set(context)
            try:
                return await handler(request)
            finally:
                self.__grpcio_context.reset(token)

        return grpc.unary_unary_rpc_method_handler(
            rpc_handler,
            request_deserializer=request_type.FromString,
            response_serializer=response_type.SerializeToString,
        )

    def _grpcio_unary_stream_rpc_method_handler(
        self,
        handler: Callable[[IProtoMessage], ServerStreamingResponse],
        request_type: type[IProtoMessage],
        response_type: type[IProtoMessage],
    ) -> grpc.RpcMethodHandler:
        async def rpc_handler(
            request: IProtoMessage,
            context: grpc.aio.ServicerContext,
        ) -> AsyncIterator[IProtoMessage]:
            token = self.__grpcio_context.set(context)
            try:
                async for response in _ensure_async_response_iterable(handler(request)):
                    yield response
            finally:
                self.__grpcio_context.reset(token)

        return grpc.unary_stream_rpc_method_handler(
            rpc_handler,
            request_deserializer=request_type.FromString,
            response_serializer=response_type.SerializeToString,
        )

    def _grpcio_stream_unary_rpc_method_handler(
        self,
        handler: Callable[[AsyncIterator[IProtoMessage]], Awaitable[T]],
        request_type: type[IProtoMessage],
        response_type: type[IProtoMessage],
    ) -> grpc.RpcMethodHandler:
        async def rpc_handler(
            request_iterator: AsyncIterator[IProtoMessage],
            context: grpc.aio.ServicerContext,
        ) -> T:
            token = self.__grpcio_context.set(context)
            try:
                return await handler(request_iterator)
            finally:
                self.__grpcio_context.reset(token)

        return grpc.stream_unary_rpc_method_handler(
            rpc_handler,
            request_deserializer=request_type.FromString,
            response_serializer=response_type.SerializeToString,
        )

    def _grpcio_stream_stream_rpc_method_handler(
        self,
        handler: Callable[[AsyncIterator[IProtoMessage]], ServerStreamingResponse],
        request_type: type[IProtoMessage],
        response_type: type[IProtoMessage],
    ) -> grpc.RpcMethodHandler:
        async def rpc_handler(
            request_iterator: AsyncIterator[IProtoMessage],
            context: grpc.aio.ServicerContext,
        ) -> AsyncIterator[IProtoMessage]:
            token = self.__grpcio_context.set(context)
            try:
                async for response in _ensure_async_response_iterable(handler(request_iterator)):
                    yield response
            finally:
                self.__grpcio_context.reset(token)

        return grpc.stream_stream_rpc_method_handler(
            rpc_handler,
            request_deserializer=request_type.FromString,
            response_serializer=response_type.SerializeToString,
        )


async def _ensure_async_response_iterable(response_iter: ServerStreamingResponse) -> AsyncIterator[IProtoMessage]:
    if isinstance(response_iter, AsyncIterable):
        iterator = response_iter.__aiter__()
        try:
            async for response in iterator:
                yield response
        finally:
            close = getattr(iterator, "aclose", None)
            if close is not None:
                await close()
    elif inspect.isawaitable(response_iter):
        result = await response_iter
        if result is not None:
            raise TypeError(SERVER_STREAMING_RETURN_ERROR)
    elif response_iter is not None:
        raise TypeError(SERVER_STREAMING_RETURN_ERROR)
