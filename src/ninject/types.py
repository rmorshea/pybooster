from __future__ import annotations

from contextvars import ContextVar
from typing import (
    TYPE_CHECKING,
    Annotated,
    Any,
    AsyncContextManager,
    AsyncIterator,
    Awaitable,
    Callable,
    ContextManager,
    Iterator,
    ParamSpec,
    TypeAlias,
    TypedDict,
    TypeVar,
    cast,
)

P = ParamSpec("P")
R = TypeVar("R")
D = TypeVar("D", bound=dict)

SyncContextProvider: TypeAlias = Callable[[], ContextManager[R]]
AsyncContextProvider: TypeAlias = Callable[[], AsyncContextManager[R]]
SyncGeneratorProvider: TypeAlias = Callable[[], Iterator[R]]
AsyncGeneratorProvider: TypeAlias = Callable[[], AsyncIterator[R]]
SyncFunctionProvider: TypeAlias = Callable[[], R]
AsyncFunctionProvider: TypeAlias = Callable[[], Awaitable[R]]

AnyProvider: TypeAlias = (
    SyncContextProvider[R]
    | AsyncContextProvider[R]
    | SyncGeneratorProvider[R]
    | AsyncGeneratorProvider[R]
    | SyncFunctionProvider[R]
    | AsyncFunctionProvider[R]
)
"""Any type of provider that can be passed to `Provider.provides`"""


def dependencies(cls: type[D]) -> type[D]:
    """Annotate a TypedDict as a dependency."""
    if issubclass(cls, dict) and TypedDict in getattr(cls, "__orig_bases__", []):
        return cast(type[D], Annotated[cls, ContextVar(cls.__name__)])
    else:
        msg = f"Expected {cls!r} to be a TypedDict"
        raise TypeError(msg)


class _DependencyAnnotation:
    def __class_getitem__(cls, item: tuple[Any, str]) -> Annotated:
        try:
            anno, name = item
        except ValueError:
            msg = f"Expected exactly two arguments, got {len(item)}"
            raise TypeError(msg) from None
        return Annotated[anno, ContextVar(name)]


if TYPE_CHECKING:
    from typing import Annotated as Dependency
else:
    Dependency = _DependencyAnnotation
