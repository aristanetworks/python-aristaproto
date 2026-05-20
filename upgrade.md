# Upgrade guide: aristaproto 0.x to 2.0

Status: draft. The grpcio AsyncIO client and server runtimes now have generator
support behind the explicit `transport=grpcio` option. The guide still tracks
the migration as draft while grpcio coverage is broadened.

## What stays the same

- Generated messages remain dataclasses subclassing `aristaproto.Message`.
- Message construction, serialization, JSON conversion, enums, oneofs, maps, and
  well-known type behavior should not require transport-driven changes.
- Generated service method names keep the current ergonomic snake_case shape.
- Server implementations still implement methods such as
  `async def do_thing(self, request) -> response`.

## Regenerate service code

For the grpcio transport, regenerate generated modules with the grpcio transport
option:

```bash
python -m grpc_tools.protoc \
  -I path/to/protos \
  --python_aristaproto_out=path/to/output \
  --python_aristaproto_opt=transport=grpcio \
  path/to/protos/*.proto
```

The legacy grpclib transport remains available during the migration window and
is still the default. Use `transport=grpclib` explicitly if you want that choice
recorded in build scripts.

## Client changes

0.x clients use `grpclib.client.Channel`:

```python
from grpclib.client import Channel

from example_pb import DoThingRequest, TestStub


channel = Channel("127.0.0.1", 50051)
client = TestStub(channel, timeout=10, metadata={"authorization": "token"})

response = await client.do_thing(DoThingRequest(name="leaf"))
channel.close()
```

2.0 grpcio clients use `grpc.aio.Channel`:

```python
import grpc

from example_pb import DoThingRequest, TestStub


channel = grpc.aio.insecure_channel("127.0.0.1:50051")
client = TestStub(
    channel,
    timeout=10,
    metadata={"authorization": "token"},
    wait_for_ready=True,
)

try:
    response = await client.do_thing(DoThingRequest(name="leaf"))
finally:
    await channel.close()
```

Client call options change from grpclib-specific options to grpcio-native
options:

- `timeout` remains supported.
- `deadline` is removed for grpcio transport; pass `timeout` instead.
- `metadata` remains supported as a mapping or collection of key/value pairs.
- `credentials` and `wait_for_ready` are grpcio-native options.
- RPC failures raise `grpc.aio.AioRpcError`, not `grpclib.GRPCError`.

Error handling changes accordingly:

```python
import grpc


try:
    await client.do_thing(DoThingRequest(name="leaf"))
except grpc.aio.AioRpcError as exc:
    if exc.code() == grpc.StatusCode.UNAUTHENTICATED:
        ...
```

For TLS, construct the channel with grpcio credentials:

```python
credentials = grpc.ssl_channel_credentials(root_certificates)
channel = grpc.aio.secure_channel("api.example.com:443", credentials)
```

## Server changes

0.x servers are registered with `grpclib.server.Server`:

```python
import grpclib.server

from example_pb import DoThingRequest, DoThingResponse, TestBase


class TestService(TestBase):
    async def do_thing(self, request: DoThingRequest) -> DoThingResponse:
        return DoThingResponse(names=[request.name])


server = grpclib.server.Server([TestService()])
await server.start("127.0.0.1", 50051)
await server.wait_closed()
```

2.0 grpcio servers are registered with `grpc.aio.server()` and the generated
service base's grpcio handler:

```python
import grpc

from example_pb import DoThingRequest, DoThingResponse, TestBase


class TestService(TestBase):
    async def do_thing(self, request: DoThingRequest) -> DoThingResponse:
        return DoThingResponse(names=[request.name])


service = TestService()
server = grpc.aio.server()
server.add_generic_rpc_handlers((service._grpcio_rpc_handler(),))
server.add_insecure_port("127.0.0.1:50051")
await server.start()
await server.wait_for_termination()
```

The generated `_grpcio_rpc_handler()` name is the intended registration hook for
grpcio generated service bases. It is prefixed to avoid collisions with proto
RPC method names.

Service method signatures stay request-focused. Do not add grpcio's
`ServicerContext` as a public method argument:

```python
class TestService(TestBase):
    async def do_many_things(self, requests):
        return DoThingResponse(names=[request.name async for request in requests])
```

When an implementation needs metadata, trailing metadata, status, or abort
behavior, use the protected grpcio context hook while handling an RPC:

```python
class TestService(TestBase):
    async def do_thing(self, request: DoThingRequest) -> DoThingResponse:
        metadata = dict(self._grpcio_context.invocation_metadata())
        if "authorization" not in metadata:
            await self._grpcio_context.abort(
                grpc.StatusCode.UNAUTHENTICATED,
                "missing authorization",
            )
        self._grpcio_context.set_trailing_metadata((("processed-by", "grpcio"),))
        return DoThingResponse(names=[request.name])
```

Unimplemented generated base methods abort with grpcio `UNIMPLEMENTED`.

## Streaming

Streaming method shapes are intended to remain ergonomic:

- Unary request, unary response: `async def method(self, request) -> response`
- Unary request, stream response:
  `async def method(self, request) -> AsyncIterator[response]`
- Stream request, unary response:
  `async def method(self, requests) -> response`
- Stream request, stream response:
  `async def method(self, requests) -> AsyncIterator[response]`

Client-streaming requests can be passed as either sync iterables or async
iterables from generated grpcio clients.

## Known migration differences

- The transport stack changes from grpclib to grpcio AsyncIO.
- grpcio uses `grpc.StatusCode` and `grpc.aio.AioRpcError`.
- grpclib `Deadline` is not part of the grpcio transport API.
- grpclib stream objects are not exposed to generated-style service methods.
- Custom code that directly depends on generated `__mapping__` needs to switch
  to grpcio server registration.
- The grpcio transport is opt-in during the migration window; generated service
  modules continue to use grpclib unless `transport=grpcio` is passed.
