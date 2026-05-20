from __future__ import annotations

from abc import ABC
from collections.abc import AsyncIterable
from typing import (
    TYPE_CHECKING,
    Any,
    AsyncIterator,
    Collection,
    Iterable,
    Mapping,
    Optional,
    Tuple,
    Type,
    Union,
)

import grpc


if TYPE_CHECKING:
    from ._types import (
        IProtoMessage,
        T,
    )


Value = Union[str, bytes]
MetadataLike = Union[Mapping[str, Value], Collection[Tuple[str, Value]]]
MessageSource = Union[Iterable["IProtoMessage"], AsyncIterable["IProtoMessage"]]


class ServiceStub(ABC):
    """
    Base class for async grpcio clients.
    """

    def __init__(
        self,
        channel: "grpc.aio.Channel",
        *,
        timeout: Optional[float] = None,
        metadata: Optional[MetadataLike] = None,
        credentials: Optional[grpc.CallCredentials] = None,
        wait_for_ready: Optional[bool] = None,
    ) -> None:
        self.channel = channel
        self.timeout = timeout
        self.metadata = metadata
        self.credentials = credentials
        self.wait_for_ready = wait_for_ready

    def __resolve_call_kwargs(
        self,
        timeout: Optional[float],
        metadata: Optional[MetadataLike],
        credentials: Optional[grpc.CallCredentials],
        wait_for_ready: Optional[bool],
    ) -> Mapping[str, Any]:
        return {
            "timeout": self.timeout if timeout is None else timeout,
            "metadata": self.__normalize_metadata(
                self.metadata if metadata is None else metadata
            ),
            "credentials": self.credentials if credentials is None else credentials,
            "wait_for_ready": (
                self.wait_for_ready if wait_for_ready is None else wait_for_ready
            ),
        }

    async def _unary_unary(
        self,
        route: str,
        request: "IProtoMessage",
        response_type: Type["T"],
        *,
        timeout: Optional[float] = None,
        metadata: Optional[MetadataLike] = None,
        credentials: Optional[grpc.CallCredentials] = None,
        wait_for_ready: Optional[bool] = None,
    ) -> "T":
        """Make a unary request and return the response."""
        call = self.channel.unary_unary(
            route,
            request_serializer=self.__serialize_message,
            response_deserializer=response_type.FromString,
        )
        return await call(
            request,
            **self.__resolve_call_kwargs(
                timeout,
                metadata,
                credentials,
                wait_for_ready,
            ),
        )

    async def _unary_stream(
        self,
        route: str,
        request: "IProtoMessage",
        response_type: Type["T"],
        *,
        timeout: Optional[float] = None,
        metadata: Optional[MetadataLike] = None,
        credentials: Optional[grpc.CallCredentials] = None,
        wait_for_ready: Optional[bool] = None,
    ) -> AsyncIterator["T"]:
        """Make a unary request and return the stream response iterator."""
        call = self.channel.unary_stream(
            route,
            request_serializer=self.__serialize_message,
            response_deserializer=response_type.FromString,
        )
        response_iterator = call(
            request,
            **self.__resolve_call_kwargs(
                timeout,
                metadata,
                credentials,
                wait_for_ready,
            ),
        )
        async for response in response_iterator:
            yield response

    async def _stream_unary(
        self,
        route: str,
        request_iterator: MessageSource,
        request_type: Type["IProtoMessage"],
        response_type: Type["T"],
        *,
        timeout: Optional[float] = None,
        metadata: Optional[MetadataLike] = None,
        credentials: Optional[grpc.CallCredentials] = None,
        wait_for_ready: Optional[bool] = None,
    ) -> "T":
        """Make a stream request and return the response."""
        call = self.channel.stream_unary(
            route,
            request_serializer=self.__serialize_message,
            response_deserializer=response_type.FromString,
        )
        return await call(
            self.__ensure_async_iterable(request_iterator),
            **self.__resolve_call_kwargs(
                timeout,
                metadata,
                credentials,
                wait_for_ready,
            ),
        )

    async def _stream_stream(
        self,
        route: str,
        request_iterator: MessageSource,
        request_type: Type["IProtoMessage"],
        response_type: Type["T"],
        *,
        timeout: Optional[float] = None,
        metadata: Optional[MetadataLike] = None,
        credentials: Optional[grpc.CallCredentials] = None,
        wait_for_ready: Optional[bool] = None,
    ) -> AsyncIterator["T"]:
        """
        Make a stream request and return an AsyncIterator to iterate over response
        messages.
        """
        call = self.channel.stream_stream(
            route,
            request_serializer=self.__serialize_message,
            response_deserializer=response_type.FromString,
        )
        response_iterator = call(
            self.__ensure_async_iterable(request_iterator),
            **self.__resolve_call_kwargs(
                timeout,
                metadata,
                credentials,
                wait_for_ready,
            ),
        )
        async for response in response_iterator:
            yield response

    @staticmethod
    def __serialize_message(message: "IProtoMessage") -> bytes:
        return message.SerializeToString()

    @staticmethod
    def __normalize_metadata(
        metadata: Optional[MetadataLike],
    ) -> Optional[Collection[Tuple[str, Value]]]:
        if metadata is None:
            return None
        if isinstance(metadata, Mapping):
            return tuple(metadata.items())
        return metadata

    @staticmethod
    async def __ensure_async_iterable(
        messages: MessageSource,
    ) -> AsyncIterator["IProtoMessage"]:
        if isinstance(messages, AsyncIterable):
            async for message in messages:
                yield message
        else:
            for message in messages:
                yield message
