from __future__ import annotations

from collections.abc import Callable
from typing import (
    Any,
    Concatenate,
    Generic,
    TypeVar,
)

from typing_extensions import (
    ParamSpec,
    Self,
)


SelfT = TypeVar("SelfT")
P = ParamSpec("P")
HybridT_co = TypeVar("HybridT_co", covariant=True)


class hybridmethod(Generic[SelfT, P, HybridT_co]):
    def __init__(
        self,
        func: Callable[
            Concatenate[type[SelfT], P], HybridT_co
        ],  # Must be the classmethod version
    ):
        self.cls_func = func
        self.__doc__ = func.__doc__

    def instancemethod(self, func: Callable[Concatenate[SelfT, P], HybridT_co]) -> Self:
        self.instance_func = func
        return self

    def __get__(
        self, instance: SelfT | None, owner: type[SelfT]
    ) -> Callable[P, HybridT_co]:
        if instance is None or self.instance_func is None:
            # either bound to the class, or no instance method available
            return self.cls_func.__get__(owner, None)
        return self.instance_func.__get__(instance, owner)


T = TypeVar("T")
TT = TypeVar("TT", bound="type[Any]")


class classproperty(Generic[TT, T]):
    def __init__(self, func: Callable[[TT], T]):
        self.__func__ = func

    def __get__(self, instance: Any, type: TT) -> T:
        return self.__func__(type)
