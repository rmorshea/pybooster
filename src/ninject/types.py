from __future__ import annotations

from collections.abc import AsyncIterator
from collections.abc import Awaitable
from collections.abc import Iterator
from contextlib import AbstractAsyncContextManager
from contextlib import AbstractContextManager
from typing import Callable
from typing import TypeAlias
from typing import TypeVar

T = TypeVar("T")

SyncContextProvider: TypeAlias = Callable[[], AbstractContextManager[T]]
AsyncContextProvider: TypeAlias = Callable[[], AbstractAsyncContextManager[T]]
SyncGeneratorProvider: TypeAlias = Callable[[], Iterator[T]]
AsyncGeneratorProvider: TypeAlias = Callable[[], AsyncIterator[T]]
SyncValueProvider: TypeAlias = Callable[[], T]
AsyncValueProvider: TypeAlias = Callable[[], Awaitable[T]]

AnyProvider: TypeAlias = (
    SyncContextProvider[T]
    | AsyncContextProvider[T]
    | SyncGeneratorProvider[T]
    | AsyncGeneratorProvider[T]
    | SyncValueProvider[T]
    | AsyncValueProvider[T]
)
"""Any type of provider that can be passed to `Provider.provides`"""
