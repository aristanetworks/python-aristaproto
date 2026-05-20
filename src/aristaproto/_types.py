from typing import (
    TYPE_CHECKING,
    Protocol,
    TypeVar,
)


if TYPE_CHECKING:
    from . import Message

    class IProtoMessage(Protocol):
        def SerializeToString(self) -> bytes: ...

        @classmethod
        def FromString(cls, data: bytes) -> "IProtoMessage": ...


# Bound type variable to allow methods to return `self` of subclasses
T = TypeVar("T", bound="Message")
ST = TypeVar("ST", bound="IProtoMessage")
