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
    TypeVar,
)

P = ParamSpec("P")
R = TypeVar("R")

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


class _DependencyAnnotation:

    def __class_getitem__(cls, item: tuple[Any, str]) -> Annotated:
        try:
            anno, name = item
        except ValueError:
            msg = f"Expected exactly two arguments, got {len(item)}"
            raise TypeError(msg) from None
        return Annotated[anno, ContextVar(name)]


if TYPE_CHECKING:
    Dependency = Annotated
    """A type hint for a dependency annotated with a context var."""
else:
    Dependency = _DependencyAnnotation
