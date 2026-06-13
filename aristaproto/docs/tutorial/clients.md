# gRPC Clients and Servers

aristaproto can generate:

  - synchronous `grpcio` clients,
  - asynchronous `grpclib` clients and server bases,
  - asynchronous `grpcio.aio` clients and server bases.

Use the runtime extra that matches the generated transport:

```sh
pip install aristaproto[grpcio]
pip install aristaproto[grpclib]
pip install aristaproto[all]
```

The examples below use this proto file:

```proto
syntax = "proto3";

package example;

message Request {
  string name = 1;
}

message Response {
  repeated string names = 1;
}

message VersionRequest {
  string name = 1;
}

message VersionResponse {
  string name = 1;
  int32 version = 2;
}

service MyService {
  rpc MyRPC(Request) returns (Response);
  rpc Upload(stream Request) returns (Response);
  rpc Versions(VersionRequest) returns (stream VersionResponse);
  rpc Chat(stream VersionRequest) returns (stream VersionResponse);
}
```

## Generation Options

Client generation is controlled with `client_generation`:

  - `none`: no clients.
  - `sync`: synchronous `grpcio` clients only. This is the default.
  - `async`: asynchronous clients only.
  - `sync_async`: both clients; async clients use the `Async` suffix.
  - `async_sync`: both clients; sync clients use the `Sync` suffix.
  - `sync_async_no_default`: both clients; sync clients use `Sync` and async clients use `Async`.

Async client transport is controlled with `client_async_transport`:

  - `grpclib`: default async client transport.
  - `grpcio`: `grpc.aio` async client transport.

Server base generation is controlled with `server_generation`:

  - `none`: no server base classes. This is the default.
  - `async`: asynchronous server base classes.

Async server transport is controlled with `server_async_transport`:

  - `grpclib`: default async server transport.
  - `grpcio`: `grpc.aio` async server transport.

## Synchronous grpcio Clients

Generate synchronous clients with the default settings or explicitly with `client_generation=sync`:

```sh
python -m grpc.tools.protoc \
  -I . \
  --python_aristaproto_out=lib \
  --python_aristaproto_opt=client_generation=sync \
  example.proto
```

Use the generated stub with a `grpc.Channel`:

```python
import grpc

from lib.example import MyServiceStub, Request


with grpc.insecure_channel("127.0.0.1:50051") as channel:
    client = MyServiceStub(channel)
    response = client.my_rpc(Request(name="hello"))
```

## Asynchronous grpclib Clients

Generate asynchronous clients with the default async transport:

```sh
python -m grpc.tools.protoc \
  -I . \
  --python_aristaproto_out=lib \
  --python_aristaproto_opt=client_generation=async \
  example.proto
```

Use the generated stub with a `grpclib.client.Channel`:

```python
from grpclib.client import Channel

from lib.example import MyServiceStub, Request


channel = Channel(host="127.0.0.1", port=50051)
try:
    client = MyServiceStub(channel)
    response = await client.my_rpc(Request(name="hello"))
finally:
    channel.close()
```

grpclib async methods accept `timeout`, `deadline`, and `metadata` keyword arguments.

## Asynchronous grpcio Clients

Generate asynchronous clients using `grpcio` AsyncIO:

```sh
python -m grpc.tools.protoc \
  -I . \
  --python_aristaproto_out=lib \
  --python_aristaproto_opt=client_generation=async \
  --python_aristaproto_opt=client_async_transport=grpcio \
  example.proto
```

Use the generated stub with a `grpc.aio.Channel`:

```python
import grpc

from lib.example import MyServiceStub, Request


async with grpc.aio.insecure_channel("127.0.0.1:50051") as channel:
    client = MyServiceStub(channel)
    response = await client.my_rpc(
        Request(name="hello"),
        timeout=2.0,
        metadata={"authorization": "bearer token"},
        wait_for_ready=True,
    )
```

grpcio AsyncIO methods accept:

  - `timeout`: a per-call timeout in seconds. This is the grpcio AsyncIO deadline API exposed as a relative timeout.
  - `metadata`: a mapping or sequence of `(key, value)` pairs. Values may be `str` or `bytes`.
  - `credentials`: optional `grpc.CallCredentials`.
  - `wait_for_ready`: optional grpcio wait-for-ready behavior.

They do not accept grpclib's `deadline` argument.

### grpcio Streaming Clients

Unary-stream methods return async iterators:

```python
import grpc

from lib.example import MyServiceStub, VersionRequest


async with grpc.aio.insecure_channel("127.0.0.1:50051") as channel:
    client = MyServiceStub(channel)
    async for response in client.versions(VersionRequest(name="hello")):
        print(response.version)
```

Client-streaming and bidirectional-streaming methods accept either synchronous or asynchronous iterables:

```python
import grpc

from lib.example import MyServiceStub, Request, VersionRequest


async def upload_requests():
    for name in ("one", "two"):
        yield Request(name=name)


async def chat_requests():
    for name in ("alpha", "beta"):
        yield VersionRequest(name=name)


async with grpc.aio.insecure_channel("127.0.0.1:50051") as channel:
    client = MyServiceStub(channel)

    upload_response = await client.upload(upload_requests())

    async for response in client.chat(chat_requests()):
        print(response.name, response.version)
```

When a grpcio streaming RPC fails or when the response iterator is closed early, aristaproto closes async request
producers that expose `aclose()`. This lets async generators run their `finally` blocks.

## Asynchronous grpcio Servers

Generate grpcio AsyncIO server base classes with:

```sh
python -m grpc.tools.protoc \
  -I . \
  --python_aristaproto_out=lib \
  --python_aristaproto_opt=server_generation=async \
  --python_aristaproto_opt=server_async_transport=grpcio \
  example.proto
```

Implement the generated base class and register its generic RPC handler with a `grpc.aio.server()`:

```python
from collections.abc import AsyncIterator

import grpc

from lib.example import (
    MyServiceBase,
    Request,
    Response,
    VersionRequest,
    VersionResponse,
)


class MyService(MyServiceBase):
    async def my_rpc(self, message: Request) -> Response:
        return Response(names=[message.name])

    async def upload(self, messages: AsyncIterator[Request]) -> Response:
        return Response(names=[message.name async for message in messages])

    async def versions(
        self,
        message: VersionRequest,
    ) -> AsyncIterator[VersionResponse]:
        for version in range(1, 4):
            yield VersionResponse(name=message.name, version=version)

    async def chat(
        self,
        messages: AsyncIterator[VersionRequest],
    ) -> AsyncIterator[VersionResponse]:
        version = 0
        async for message in messages:
            version += 1
            yield VersionResponse(name=message.name, version=version)


server = grpc.aio.server()
service = MyService()
server.add_generic_rpc_handlers((service._grpcio_rpc_handler(),))
server.add_insecure_port("127.0.0.1:50051")
await server.start()
await server.wait_for_termination()
```

### Server-Streaming Return Rules

Server-streaming and bidirectional-streaming methods must return an `AsyncIterable` of response messages. The usual
pattern is to implement them as async generators:

```python
async def versions(self, message: VersionRequest) -> AsyncIterator[VersionResponse]:
    yield VersionResponse(name=message.name, version=1)
```

At runtime, returning `None` is allowed and produces no responses, although async generators are preferred for generated
service subclasses because their method signatures are typed as async iterators:

```python
async def versions(self, message: VersionRequest):
    return None
```

Do not implement server-streaming methods as plain `async def` functions that return a response, a list, or another
async iterable:

```python
async def versions(self, message: VersionRequest):
    return [VersionResponse(name=message.name, version=1)]  # Raises TypeError.
```

This is rejected because returning values from a coroutine is easy to confuse with yielding streamed responses.

### Server Context and Deadlines

During a grpcio AsyncIO request, service methods can access the native `grpc.aio.ServicerContext` with
`self._grpcio_context`:

```python
async def my_rpc(self, message: Request) -> Response:
    remaining = self._grpcio_context.time_remaining()
    metadata = dict(self._grpcio_context.invocation_metadata())
    return Response(names=[metadata.get("request-id", ""), str(remaining)])
```

Clients set RPC deadlines by passing `timeout=...` to generated grpcio AsyncIO client methods. A server cannot extend or
replace an incoming client deadline after the call starts. For server-enforced limits, wrap handler work with
`asyncio.timeout()`:

```python
import asyncio


async def my_rpc(self, message: Request) -> Response:
    async with asyncio.timeout(2.0):
        return await do_work(message)
```

For long-lived streams, combine client timeouts with service-side cancellation-aware code. If a client neither cancels
nor closes a stalled request stream, the handler may wait until grpcio flow control, the client deadline, or your own
server timeout interrupts the work.
