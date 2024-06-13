from __future__ import annotations

from typing import (
    AsyncContextManager,
    AsyncIterator,
    Awaitable,
    Callable,
    ContextManager,
    Iterator,
    TypeAlias,
    TypeVar,
)

T = TypeVar("T")

SyncContextProvider: TypeAlias = Callable[[], ContextManager[T]]
AsyncContextProvider: TypeAlias = Callable[[], AsyncContextManager[T]]
SyncGeneratorProvider: TypeAlias = Callable[[], Iterator[T]]
AsyncGeneratorProvider: TypeAlias = Callable[[], AsyncIterator[T]]
SyncFunctionProvider: TypeAlias = Callable[[], T]
AsyncFunctionProvider: TypeAlias = Callable[[], Awaitable[T]]

AnyProvider: TypeAlias = (
    SyncContextProvider[T]
    | AsyncContextProvider[T]
    | SyncGeneratorProvider[T]
    | AsyncGeneratorProvider[T]
    | SyncFunctionProvider[T]
    | AsyncFunctionProvider[T]
)
"""Any type of provider that can be passed to `Provider.provides`"""
