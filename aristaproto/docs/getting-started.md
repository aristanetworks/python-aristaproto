Getting Started
===============

## Compilation


### Install protoc

The aristaproto compiler is a plugin of `protoc`, you first need to [install](https://grpc.io/docs/protoc-installation/) it.

You can also use it from `grpcio-tools`:

```sh
pip install grpcio-tools
```

### Install `aristaproto_compiler`

It is possible to install `aristaproto_compiler` using pip:

```
pip install aristaproto_compiler
```

### Compile a proto file

Create the following `example.proto` file.

```proto
syntax = "proto3";

package helloworld;

message HelloWorld {
    string message = 1;
}

service HelloService {
    rpc SayHello (HelloWorld) returns (HelloWorld);
}
```

You should be able to compile it using:

```
mkdir lib
protoc -I . --python_aristaproto_out=lib example.proto
```

If you installed `protoc` with `grpc-tools`, the command will be:

```
mkdir lib
python -m grpc.tools.protoc -I . --python_aristaproto_out=lib example.proto
```

#### Service compilation

##### Clients

By default, for each service, aristaproto will generate a synchronous client. Both synchronous and asynchronous clients
are supported.

  - Synchronous clients rely on the `grpcio` package. Make sure to enable the `grpcio` extra package when installing
    aristaproto to use them.
  - Asynchronous clients use `grpclib` by default. Make sure to enable the `grpclib` extra package when using the
    default async transport.
  - Asynchronous clients can also use `grpcio` AsyncIO by setting `client_async_transport=grpcio`. Make sure to enable
    the `grpcio` extra package when using this transport.

To choose which clients to generate, use the `client_generation` option of aristaproto. It supports the following
values:

  - `none`: Clients are not generated.
  - `sync`: Only synchronous clients are generated.
  - `async`: Only asynchronous clients are generated.
  - `sync_async`: Both synchronous and asynchronous clients are generated.
        Asynchronous clients are generated with the Async suffix.
  - `async_sync`: Both synchronous and asynchronous clients are generated.
        Synchronous clients are generated with the Sync suffix.
  - `sync_async_no_default`: Both synchronous and asynchronous clients are generated.
        Synchronous clients are generated with the Sync suffix, and asynchronous clients are generated with the Async
        suffix.

For example, this will only generate asynchronous clients using the default `grpclib` transport:

```sh
protoc -I . \
  --python_aristaproto_out=lib \
  --python_aristaproto_opt=client_generation=async \
  example.proto
```

To generate asynchronous clients using `grpcio` AsyncIO, also set `client_async_transport=grpcio`:

```sh
protoc -I . \
  --python_aristaproto_out=lib \
  --python_aristaproto_opt=client_generation=async \
  --python_aristaproto_opt=client_async_transport=grpcio \
  example.proto
```

##### Servers

By default, aristaproto will not generate server base classes. To enable them, set the `server_generation` option to
`async` with `--python_aristaproto_opt=server_generation=async`.

These base classes use `grpclib` by default. To generate server bases using `grpcio` AsyncIO, also set
`server_async_transport=grpcio`:

```sh
protoc -I . \
  --python_aristaproto_out=lib \
  --python_aristaproto_opt=server_generation=async \
  --python_aristaproto_opt=server_async_transport=grpcio \
  example.proto
```

Use the matching runtime extra for the selected transport: `aristaproto[grpclib]` or `aristaproto[grpcio]`.


## Installation

The package `aristaproto` can be installed from PyPI using `pip`:

```sh
pip install aristaproto[all]
```

The optional extras are:

  - `aristaproto[grpcio]` for synchronous `grpcio` clients and asynchronous `grpcio.aio` clients and servers.
  - `aristaproto[grpclib]` for asynchronous `grpclib` clients and servers.
  - `aristaproto[all]` for all supported runtime extras.

!!! warning
    Make sure that the proto files were generated with a version of `aristaproto_compiler` that is compatible with your
    version of `aristaproto`.

    The version `0.x.y` of `aristaproto` is compatible with the version `0.a.b` of the compiler if and only if `a=b`.

## Basic usage

If you successfully compiled the `example.proto` file from the compiler documentation, you should now be able to use it!

```python
>>> from lib.helloworld import HelloWorld
>>> msg = HelloWorld(message="Hello world!")
>>> msg
HelloWorld(message='Hello world!')
>>> bytes(msg)
b'\n\x0cHello world!'
>>> msg.to_dict()
{'message': 'Hello world!'}
```

## gRPC support

The generated code can include client stubs and server base classes for RPC services declared in proto files.
Synchronous clients use `grpcio`. Asynchronous clients and servers can use either `grpclib` or `grpcio` AsyncIO.


Given a service definition similar to the one below:

```proto
syntax = "proto3";

package echo;

message EchoRequest {
    string value = 1;
    // Number of extra times to echo
    uint32 extra_times = 2;
}

message EchoResponse {
    repeated string values = 1;
}

message EchoStreamResponse  {
    string value = 1;
}

service Echo {
    rpc Echo(EchoRequest) returns (EchoResponse);
    rpc EchoStream(EchoRequest) returns (stream EchoStreamResponse);
}
```

### Async grpclib client

```python
import asyncio
from grpclib.client import Channel
from echo import EchoRequest, EchoStub


async def main():
    channel = Channel(host="127.0.0.1", port=50051)
    service = EchoStub(channel)
    response = await service.echo(EchoRequest(value="hello", extra_times=1))
    print(response)

    async for response in service.echo_stream(EchoRequest(value="hello", extra_times=1)):
        print(response)

    channel.close()

asyncio.run(main())
```

### Async grpcio client

Generate the client with `client_generation=async,client_async_transport=grpcio`.

```python
import grpc

from echo import EchoRequest, EchoStub


async with grpc.aio.insecure_channel("127.0.0.1:50051") as channel:
    client = EchoStub(channel)
    response = await client.echo(EchoRequest(value="hello", extra_times=1), timeout=2.0)

    async for response in client.echo_stream(EchoRequest(value="hello", extra_times=1)):
        print(response)
```

### Async grpcio server

Generate the base class with `server_generation=async,server_async_transport=grpcio`.

```python
from typing import AsyncIterator

import grpc

from echo import EchoBase, EchoRequest, EchoResponse, EchoStreamResponse


class EchoService(EchoBase):
    async def echo(self, message: EchoRequest) -> EchoResponse:
        return EchoResponse(values=[message.value])

    async def echo_stream(
        self, message: EchoRequest
    ) -> AsyncIterator[EchoStreamResponse]:
        for _ in range(message.extra_times + 1):
            yield EchoStreamResponse(value=message.value)


async def start_server():
    server = grpc.aio.server()
    service = EchoService()
    server.add_generic_rpc_handlers((service._grpcio_rpc_handler(),))
    server.add_insecure_port("127.0.0.1:50051")
    await server.start()
    await server.wait_for_termination()
```

## JSON

Message objects include `aristaproto.Message.to_json` and
`aristaproto.Message.from_json` methods for JSON (de)serialisation, and
`aristaproto.Message.to_dict`, `aristaproto.Message.from_dict` for
converting back and forth from JSON serializable dicts.

`google.protobuf.Timestamp` fields use timezone-aware `datetime.datetime`
values. When binary or JSON data contains sub-microsecond precision,
aristaproto preserves it by returning a `aristaproto.nano_datetime.NanoDatetime`,
which is a `datetime.datetime` subclass. Timestamp JSON accepts and emits
RFC 3339 strings with up to 9 fractional second digits.

For compatibility the default is to convert field names to
`aristaproto.Casing.CAMEL`. You can control this behavior by passing a
different casing value, e.g:

```python
@dataclass
class MyMessage(aristaproto.Message):
    a_long_field_name: str = aristaproto.string_field(1)


>>> test = MyMessage(a_long_field_name="Hello World!")
>>> test.to_dict(aristaproto.Casing.SNAKE)
{"a_long_field_name": "Hello World!"}
>>> test.to_dict(aristaproto.Casing.CAMEL)
{"aLongFieldName": "Hello World!"}

>>> test.to_json(indent=2)
'{\n  "aLongFieldName": "Hello World!"\n}'

>>> test.from_dict({"aLongFieldName": "Goodbye World!"})
>>> test.a_long_field_name
"Goodbye World!"
```
