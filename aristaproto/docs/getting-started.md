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
  - Asynchronous clients rely on the `grpclib` package. Make sure to enable the `grpclib` extra package when installing
    aristaproto to use them.

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

For example, `protoc -I . --python_aristaproto_out=lib example.proto --python_aristaproto_opt=client_generation=async`
will only generate asynchronous clients.

##### Servers

By default, aristaproto will not generate server base classes. To enable them, set the `server_generation` option to
`async` with `--python_aristaproto_opt=server_generation=async`.

These base classes will be asynchronous and rely on `grpclib`. To use them, make sure to install `aristaproto` with the
`grpclib` extra package.


## Installation

The package `aristaproto` can be installed from PyPI using `pip`:

```sh
pip install aristaproto[all]
```

!!! warning
    Make sure that the proto files were generated with a version of `aristaproto_compiler` that is compatible with your
    version of `aristaproto`.

    The version `0.x.y` of `aristaproto` is compatible with the version `0.a.b` of the compiler if and only if `a=b`.

## Basic usage

If you successfuly compiled the `example.proto` file from the compiler documentation, you should now be able to use it!

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

!!! Warning
    The rest of the documentation is not up to date.


## Async gRPC Support

The generated code includes [grpclib](https://grpclib.readthedocs.io/en/latest) based
stub (client and server) classes for rpc services declared in the input proto files.
It is enabled by default.


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

The generated client can be used like so:

```python
import asyncio
from grpclib.client import Channel
import echo


async def main():
    channel = Channel(host="127.0.0.1", port=50051)
    service = echo.EchoStub(channel)
    response = await service.echo(value="hello", extra_times=1)
    print(response)

    async for response in service.echo_stream(value="hello", extra_times=1):
        print(response)

    # don't forget to close the channel when you're done!
    channel.close()

asyncio.run(main())

# outputs
EchoResponse(values=['hello', 'hello'])
EchoStreamResponse(value='hello')
EchoStreamResponse(value='hello')
```


The server-facing stubs can be used to implement a Python
gRPC server.
To use them, simply subclass the base class in the generated files and override the
service methods:

```python
from echo import EchoBase
from grpclib.server import Server
from typing import AsyncIterator


class EchoService(EchoBase):
    async def echo(self, value: str, extra_times: int) -> "EchoResponse":
        return value

    async def echo_stream(
        self, value: str, extra_times: int
    ) -> AsyncIterator["EchoStreamResponse"]:
        for _ in range(extra_times):
            yield value


async def start_server():
    HOST = "127.0.0.1"
    PORT = 1337
    server = Server([EchoService()])
    await server.start(HOST, PORT)
    await server.serve_forever()
```

## JSON

Message objects include `aristaproto.Message.to_json` and
`aristaproto.Message.from_json` methods for JSON (de)serialisation, and
`aristaproto.Message.to_dict`, `aristaproto.Message.from_dict` for
converting back and forth from JSON serializable dicts.

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
