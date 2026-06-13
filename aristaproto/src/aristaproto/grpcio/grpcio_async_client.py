from __future__ import annotations

from abc import ABC
from collections.abc import AsyncIterable, AsyncIterator, Collection, Iterable, Iterator, Mapping
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    import grpc
    import grpc.aio

    from aristaproto._types import IProtoMessage, T


Value = str | bytes
MetadataLike = Mapping[str, Value] | Collection[tuple[str, Value]]
MessageSource = Iterable["IProtoMessage"] | AsyncIterable["IProtoMessage"]


class ServiceStub(ABC):
    """
    Base class for async grpcio clients.
    """

    def __init__(
        self,
        channel: grpc.aio.Channel,
        *,
        timeout: float | None = None,
        metadata: MetadataLike | None = None,
        credentials: grpc.CallCredentials | None = None,
        wait_for_ready: bool | None = None,
    ) -> None:
        self.channel = channel
        self.timeout = timeout
        self.metadata = metadata
        self.credentials = credentials
        self.wait_for_ready = wait_for_ready

    def __resolve_call_kwargs(
        self,
        timeout: float | None,
        metadata: MetadataLike | None,
        credentials: grpc.CallCredentials | None,
        wait_for_ready: bool | None,
    ) -> dict[str, Any]:
        return {
            "timeout": self.timeout if timeout is None else timeout,
            "metadata": _normalize_metadata(self.metadata if metadata is None else metadata),
            "credentials": self.credentials if credentials is None else credentials,
            "wait_for_ready": self.wait_for_ready if wait_for_ready is None else wait_for_ready,
        }

    async def _unary_unary(
        self,
        route: str,
        request: IProtoMessage,
        response_type: type[T],
        *,
        timeout: float | None = None,
        metadata: MetadataLike | None = None,
        credentials: grpc.CallCredentials | None = None,
        wait_for_ready: bool | None = None,
    ) -> T:
        """Make a unary request and return the response."""
        rpc = self.channel.unary_unary(
            route,
            request_serializer=type(request).SerializeToString,
            response_deserializer=response_type.FromString,
        )
        return await rpc(
            request,
            **self.__resolve_call_kwargs(timeout, metadata, credentials, wait_for_ready),
        )

    async def _unary_stream(
        self,
        route: str,
        request: IProtoMessage,
        response_type: type[T],
        *,
        timeout: float | None = None,
        metadata: MetadataLike | None = None,
        credentials: grpc.CallCredentials | None = None,
        wait_for_ready: bool | None = None,
    ) -> AsyncIterator[T]:
        """Make a unary request and return the stream response iterator."""
        rpc = self.channel.unary_stream(
            route,
            request_serializer=type(request).SerializeToString,
            response_deserializer=response_type.FromString,
        )
        call = rpc(
            request,
            **self.__resolve_call_kwargs(timeout, metadata, credentials, wait_for_ready),
        )
        try:
            async for message in call:
                yield message
        finally:
            if not call.done():
                call.cancel()

    async def _stream_unary(
        self,
        route: str,
        request_iterator: MessageSource,
        request_type: type[IProtoMessage],
        response_type: type[T],
        *,
        timeout: float | None = None,
        metadata: MetadataLike | None = None,
        credentials: grpc.CallCredentials | None = None,
        wait_for_ready: bool | None = None,
    ) -> T:
        """Make a stream request and return the response."""
        rpc = self.channel.stream_unary(
            route,
            request_serializer=request_type.SerializeToString,
            response_deserializer=response_type.FromString,
        )
        request_messages = _AsyncMessageSourceIterator(request_iterator)
        call = rpc(
            request_messages,
            **self.__resolve_call_kwargs(timeout, metadata, credentials, wait_for_ready),
        )
        try:
            return await call
        finally:
            if not call.done():
                call.cancel()
            await request_messages.aclose()

    async def _stream_stream(
        self,
        route: str,
        request_iterator: MessageSource,
        request_type: type[IProtoMessage],
        response_type: type[T],
        *,
        timeout: float | None = None,
        metadata: MetadataLike | None = None,
        credentials: grpc.CallCredentials | None = None,
        wait_for_ready: bool | None = None,
    ) -> AsyncIterator[T]:
        """
        Make a stream request and return an AsyncIterator to iterate over response
        messages.
        """
        rpc = self.channel.stream_stream(
            route,
            request_serializer=request_type.SerializeToString,
            response_deserializer=response_type.FromString,
        )
        request_messages = _AsyncMessageSourceIterator(request_iterator)
        call = rpc(
            request_messages,
            **self.__resolve_call_kwargs(timeout, metadata, credentials, wait_for_ready),
        )
        try:
            async for message in call:
                yield message
        finally:
            if not call.done():
                call.cancel()
            await request_messages.aclose()


def _normalize_metadata(metadata: MetadataLike | None) -> tuple[tuple[str, Value], ...] | None:
    if metadata is None:
        return None

    if isinstance(metadata, Mapping):
        return cast("tuple[tuple[str, Value], ...]", tuple(metadata.items()))

    return cast("tuple[tuple[str, Value], ...]", tuple(metadata))


class _AsyncMessageSourceIterator(AsyncIterator[Any]):
    def __init__(self, messages: MessageSource) -> None:
        self._messages = messages
        self._iterator: AsyncIterator[IProtoMessage] | Iterator[IProtoMessage] | None = None
        self._closed = False
        self._close_called = False
        self._iterating = False

    def __aiter__(self) -> _AsyncMessageSourceIterator:
        return self

    async def __anext__(self) -> IProtoMessage:
        if self._closed:
            raise StopAsyncIteration

        self._iterating = True
        try:
            message = await self._next_message()
        except StopAsyncIteration:
            self._iterating = False
            await self.aclose()
            raise
        except BaseException:
            self._iterating = False
            if self._closed:
                await self._close_iterator()
            raise

        self._iterating = False
        if self._closed:
            await self._close_iterator()
            raise StopAsyncIteration
        return message

    async def _next_message(self) -> IProtoMessage:
        iterator = self._get_iterator()
        if isinstance(self._messages, AsyncIterable):
            return await anext(cast("AsyncIterator[IProtoMessage]", iterator))

        try:
            return next(cast("Iterator[IProtoMessage]", iterator))
        except StopIteration:
            raise StopAsyncIteration from None

    def _get_iterator(self) -> AsyncIterator[IProtoMessage] | Iterator[IProtoMessage]:
        if self._iterator is None:
            if isinstance(self._messages, AsyncIterable):
                self._iterator = self._messages.__aiter__()
            else:
                self._iterator = iter(self._messages)
        return self._iterator

    async def aclose(self) -> None:
        self._closed = True
        if not self._iterating:
            await self._close_iterator()

    async def _close_iterator(self) -> None:
        if self._close_called:
            return

        self._close_called = True
        iterator = self._iterator
        if iterator is None:
            return

        close = getattr(iterator, "aclose", None)
        if close is not None:
            await close()
            return

        close = getattr(iterator, "close", None)
        if close is not None:
            close()
