from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Iterator
from contextlib import AsyncContextManager, ContextManager
from typing import (
    Callable,
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
