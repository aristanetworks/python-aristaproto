from __future__ import annotations

from abc import ABC
from collections.abc import AsyncIterable
from contextvars import ContextVar
from typing import (
    TYPE_CHECKING,
    Any,
    AsyncIterator,
    Callable,
    Mapping,
    NoReturn,
    Type,
)

import grpc


if TYPE_CHECKING:
    from ._types import (
        IProtoMessage,
        T,
    )


ContextVarToken = Any
UnaryUnaryHandler = Callable[["IProtoMessage"], Any]
UnaryStreamHandler = Callable[["IProtoMessage"], AsyncIterable["IProtoMessage"]]
StreamUnaryHandler = Callable[[AsyncIterator["IProtoMessage"]], Any]
StreamStreamHandler = Callable[
    [AsyncIterator["IProtoMessage"]], AsyncIterable["IProtoMessage"]
]


class ServiceBase(ABC):
    """
    Base class for async grpcio servers.
    """

    __grpcio_context: ContextVar[grpc.aio.ServicerContext | None] = ContextVar(
        "aristaproto_grpcio_servicer_context",
        default=None,
    )

    @property
    def _grpcio_context(self) -> grpc.aio.ServicerContext:
        """
        Return the grpcio context for the current RPC handler.

        Generated service method signatures stay ergonomic and receive only
        aristaproto request messages or request iterators. Implementations that
        need grpcio metadata, status, or cancellation APIs can use this
        protected hook while a runtime handler is executing.
        """
        context = self.__grpcio_context.get()
        if context is None:
            raise RuntimeError(
                "grpcio servicer context is only available inside RPC handlers"
            )
        return context

    def _grpcio_generic_rpc_handler(
        self,
        service_name: str,
        method_handlers: Mapping[str, grpc.RpcMethodHandler],
    ) -> grpc.GenericRpcHandler:
        return grpc.method_handlers_generic_handler(service_name, method_handlers)

    def _grpcio_unary_unary_rpc_method_handler(
        self,
        handler: UnaryUnaryHandler,
        request_type: Type["IProtoMessage"],
        response_type: Type["T"],
    ) -> grpc.RpcMethodHandler:
        return grpc.unary_unary_rpc_method_handler(
            self.__call_rpc_handler_unary_unary(handler),
            request_deserializer=request_type.FromString,
            response_serializer=response_type.SerializeToString,
        )

    def _grpcio_unary_stream_rpc_method_handler(
        self,
        handler: UnaryStreamHandler,
        request_type: Type["IProtoMessage"],
        response_type: Type["IProtoMessage"],
    ) -> grpc.RpcMethodHandler:
        return grpc.unary_stream_rpc_method_handler(
            self.__call_rpc_handler_unary_stream(handler),
            request_deserializer=request_type.FromString,
            response_serializer=response_type.SerializeToString,
        )

    def _grpcio_stream_unary_rpc_method_handler(
        self,
        handler: StreamUnaryHandler,
        request_type: Type["IProtoMessage"],
        response_type: Type["T"],
    ) -> grpc.RpcMethodHandler:
        return grpc.stream_unary_rpc_method_handler(
            self.__call_rpc_handler_stream_unary(handler),
            request_deserializer=request_type.FromString,
            response_serializer=response_type.SerializeToString,
        )

    def _grpcio_stream_stream_rpc_method_handler(
        self,
        handler: StreamStreamHandler,
        request_type: Type["IProtoMessage"],
        response_type: Type["IProtoMessage"],
    ) -> grpc.RpcMethodHandler:
        return grpc.stream_stream_rpc_method_handler(
            self.__call_rpc_handler_stream_stream(handler),
            request_deserializer=request_type.FromString,
            response_serializer=response_type.SerializeToString,
        )

    async def _grpcio_unimplemented(self, method_name: str) -> NoReturn:
        await self._grpcio_context.abort(
            grpc.StatusCode.UNIMPLEMENTED,
            f"Method {method_name} is unimplemented",
        )
        raise AssertionError("grpcio ServicerContext.abort returned unexpectedly")

    def __call_rpc_handler_unary_unary(
        self,
        handler: UnaryUnaryHandler,
    ) -> Callable[["IProtoMessage", grpc.aio.ServicerContext], Any]:
        async def call_handler(
            request: "IProtoMessage",
            context: grpc.aio.ServicerContext,
        ) -> "IProtoMessage":
            token = self.__set_grpcio_context(context)
            try:
                return await handler(request)
            finally:
                self.__reset_grpcio_context(token)

        return call_handler

    def __call_rpc_handler_unary_stream(
        self,
        handler: UnaryStreamHandler,
    ) -> Callable[
        ["IProtoMessage", grpc.aio.ServicerContext], AsyncIterator["IProtoMessage"]
    ]:
        async def call_handler(
            request: "IProtoMessage",
            context: grpc.aio.ServicerContext,
        ) -> AsyncIterator["IProtoMessage"]:
            token = self.__set_grpcio_context(context)
            try:
                async for response in handler(request):
                    yield response
            finally:
                self.__reset_grpcio_context(token)

        return call_handler

    def __call_rpc_handler_stream_unary(
        self,
        handler: StreamUnaryHandler,
    ) -> Callable[[AsyncIterator["IProtoMessage"], grpc.aio.ServicerContext], Any]:
        async def call_handler(
            request_iterator: AsyncIterator["IProtoMessage"],
            context: grpc.aio.ServicerContext,
        ) -> "IProtoMessage":
            token = self.__set_grpcio_context(context)
            try:
                return await handler(request_iterator)
            finally:
                self.__reset_grpcio_context(token)

        return call_handler

    def __call_rpc_handler_stream_stream(
        self,
        handler: StreamStreamHandler,
    ) -> Callable[
        [AsyncIterator["IProtoMessage"], grpc.aio.ServicerContext],
        AsyncIterator["IProtoMessage"],
    ]:
        async def call_handler(
            request_iterator: AsyncIterator["IProtoMessage"],
            context: grpc.aio.ServicerContext,
        ) -> AsyncIterator["IProtoMessage"]:
            token = self.__set_grpcio_context(context)
            try:
                async for response in handler(request_iterator):
                    yield response
            finally:
                self.__reset_grpcio_context(token)

        return call_handler

    @classmethod
    def __set_grpcio_context(
        cls,
        context: grpc.aio.ServicerContext,
    ) -> ContextVarToken:
        return cls.__grpcio_context.set(context)

    @classmethod
    def __reset_grpcio_context(cls, token: ContextVarToken) -> None:
        cls.__grpcio_context.reset(token)
