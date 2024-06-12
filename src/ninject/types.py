from __future__ import annotations

from typing import (
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
