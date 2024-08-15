import sys
from collections.abc import Awaitable
from collections.abc import Sequence
from contextlib import AbstractAsyncContextManager
from contextlib import AbstractContextManager
from functools import wraps
from typing import Any
from typing import Callable
from typing import TypeVar

from ninject.types import AsyncContextProvider
from ninject.types import SyncContextProvider

T = TypeVar("T")


def exhaust_callbacks(callbacks: Sequence[Callable[[], Any]]) -> None:
    cb, *rest = callbacks
    try:
        cb()
    finally:
        if rest:
            exhaust_callbacks(rest)


def exhaust_exits(ctxts: Sequence[AbstractContextManager]) -> None:
    if not ctxts:
        return
    c, *rest = ctxts
    try:
        c.__exit__(*sys.exc_info())
    except Exception:
        exhaust_exits(rest)
        raise
    else:
        exhaust_exits(rest)


async def async_exhaust_exits(ctxts: Sequence[AbstractAsyncContextManager[Any]]) -> None:
    if not ctxts:
        return
    c, *rest = ctxts
    try:
        await c.__aexit__(*sys.exc_info())
    except Exception:
        await async_exhaust_exits(rest)
        raise
    else:
        await async_exhaust_exits(rest)


def asyncfunctioncontextmanager(func: Callable[[], Awaitable[T]]) -> AsyncContextProvider[T]:
    return wraps(func)(lambda: AsyncFunctionContextManager(func))


def syncfunctioncontextmanager(func: Callable[[], T]) -> SyncContextProvider[T]:
    return wraps(func)(lambda: SyncFunctionContextManager(func))


class AsyncFunctionContextManager(AbstractAsyncContextManager[T]):
    def __init__(self, func: Callable[[], Awaitable[T]]) -> None:
        self.func = func

    async def __aenter__(self) -> T:
        return await self.func()

    async def __aexit__(self, etype: Any, evalue: Any, atrace: Any, /) -> None:
        pass


class SyncFunctionContextManager(AbstractContextManager[T]):
    def __init__(self, func: Callable[[], T]) -> None:
        self.func = func

    def __enter__(self) -> T:
        return self.func()

    def __exit__(self, etype: Any, evalue: Any, atrace: Any, /) -> None:
        pass


def sentinel(name: str) -> Any:
    """Create a sentinel object with the given name."""
    return type(name, (), {"__repr__": lambda _: name})()
