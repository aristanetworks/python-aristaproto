API reference
=============

The following document outlines aristaproto's API. These classes should not be extended manually unless the generated
code explicitly inherits from them.


## Message

::: aristaproto.Message

::: aristaproto.which_one_of


## Enumerations

::: aristaproto.Enum

::: aristaproto.Casing


## gRPC Runtime Helpers

Generated synchronous clients use `grpcio` directly. Generated asynchronous clients and server bases use these runtime
base classes when `client_async_transport=grpcio` or `server_async_transport=grpcio` is selected.

::: aristaproto.grpcio.ServiceStub

::: aristaproto.grpcio.ServiceBase

Generated asynchronous `grpclib` clients and server bases use these runtime base classes when the default async
transport is selected.

::: aristaproto.grpclib.ServiceStub

::: aristaproto.grpclib.ServiceBase
