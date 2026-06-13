from typing import TYPE_CHECKING, Protocol, TypeVar

if TYPE_CHECKING:
    from grpclib._typing import IProtoMessage  # type: ignore[reportPrivateImportUsage]

    from . import Message


GrpcioProtoMessageT = TypeVar("GrpcioProtoMessageT", bound="GrpcioProtoMessage")


class GrpcioProtoMessage(Protocol):
    @classmethod
    def FromString(cls: type[GrpcioProtoMessageT], s: bytes) -> GrpcioProtoMessageT: ...

    def SerializeToString(self) -> bytes: ...


# Bound type variable to allow methods to return `self` of subclasses
T = TypeVar("T", bound="Message")
ST = TypeVar("ST", bound="IProtoMessage")
