from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Iterator
from contextlib import AbstractAsyncContextManager, AbstractContextManager
from typing import (
    Callable,
    TypeAlias,
    TypeVar,
)

T = TypeVar("T")

SyncContextProvider: TypeAlias = Callable[[], AbstractContextManager[T]]
AsyncContextProvider: TypeAlias = Callable[[], AbstractAsyncContextManager[T]]
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
