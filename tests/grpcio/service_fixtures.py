from __future__ import annotations

from typing import (
    AsyncIterable,
    AsyncIterator,
    Iterable,
    Optional,
    Union,
)

import grpc

from aristaproto.grpcio_client import (
    MetadataLike,
    ServiceStub,
)
from tests.output_aristaproto.service import (
    DoThingRequest,
    DoThingResponse,
    GetThingRequest,
    GetThingResponse,
)


DO_THING_ROUTE = "/service.Test/DoThing"
DO_MANY_THINGS_ROUTE = "/service.Test/DoManyThings"
GET_THING_VERSIONS_ROUTE = "/service.Test/GetThingVersions"
GET_DIFFERENT_THINGS_ROUTE = "/service.Test/GetDifferentThings"


class GeneratedStyleTestStub(ServiceStub):
    async def do_thing(
        self,
        do_thing_request: DoThingRequest,
        *,
        timeout: Optional[float] = None,
        metadata: Optional[MetadataLike] = None,
        credentials: Optional[grpc.CallCredentials] = None,
        wait_for_ready: Optional[bool] = None,
    ) -> DoThingResponse:
        return await self._unary_unary(
            DO_THING_ROUTE,
            do_thing_request,
            DoThingResponse,
            timeout=timeout,
            metadata=metadata,
            credentials=credentials,
            wait_for_ready=wait_for_ready,
        )

    async def do_many_things(
        self,
        do_thing_request_iterator: Union[
            AsyncIterable[DoThingRequest],
            Iterable[DoThingRequest],
        ],
        *,
        timeout: Optional[float] = None,
        metadata: Optional[MetadataLike] = None,
        credentials: Optional[grpc.CallCredentials] = None,
        wait_for_ready: Optional[bool] = None,
    ) -> DoThingResponse:
        return await self._stream_unary(
            DO_MANY_THINGS_ROUTE,
            do_thing_request_iterator,
            DoThingRequest,
            DoThingResponse,
            timeout=timeout,
            metadata=metadata,
            credentials=credentials,
            wait_for_ready=wait_for_ready,
        )

    async def get_thing_versions(
        self,
        get_thing_request: GetThingRequest,
        *,
        timeout: Optional[float] = None,
        metadata: Optional[MetadataLike] = None,
        credentials: Optional[grpc.CallCredentials] = None,
        wait_for_ready: Optional[bool] = None,
    ) -> AsyncIterator[GetThingResponse]:
        async for response in self._unary_stream(
            GET_THING_VERSIONS_ROUTE,
            get_thing_request,
            GetThingResponse,
            timeout=timeout,
            metadata=metadata,
            credentials=credentials,
            wait_for_ready=wait_for_ready,
        ):
            yield response

    async def get_different_things(
        self,
        get_thing_request_iterator: Union[
            AsyncIterable[GetThingRequest],
            Iterable[GetThingRequest],
        ],
        *,
        timeout: Optional[float] = None,
        metadata: Optional[MetadataLike] = None,
        credentials: Optional[grpc.CallCredentials] = None,
        wait_for_ready: Optional[bool] = None,
    ) -> AsyncIterator[GetThingResponse]:
        async for response in self._stream_stream(
            GET_DIFFERENT_THINGS_ROUTE,
            get_thing_request_iterator,
            GetThingRequest,
            GetThingResponse,
            timeout=timeout,
            metadata=metadata,
            credentials=credentials,
            wait_for_ready=wait_for_ready,
        ):
            yield response


async def async_do_thing_requests(
    names: Iterable[str],
) -> AsyncIterator[DoThingRequest]:
    for name in names:
        yield DoThingRequest(name=name)


async def async_get_thing_requests(
    names: Iterable[str],
) -> AsyncIterator[GetThingRequest]:
    for name in names:
        yield GetThingRequest(name=name)


async def collect_get_thing_responses(
    iterator: AsyncIterator[GetThingResponse],
) -> list[GetThingResponse]:
    return [message async for message in iterator]
