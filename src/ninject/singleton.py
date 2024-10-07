from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from contextlib import AbstractContextManager
from typing import TYPE_CHECKING
from typing import TypeVar

from ninject._private._singleton import async_singleton
from ninject._private._singleton import sync_singleton
from ninject._private._utils import normalize_dependency

if TYPE_CHECKING:
    from collections.abc import Sequence

T = TypeVar("T")


def singleton(cls: type[T] | Sequence) -> _SingletonContext[T]:
    """Declare that a dependency should be a singleton for the duration of the context."""
    return _SingletonContext(normalize_dependency(cls))


class _SingletonContext(AbstractContextManager[T], AbstractAsyncContextManager[T]):
    """A context manager to declare a singleton instance of a dependency."""

    def __init__(self, types: Sequence[type[T]]) -> None:
        self.types = types

    def __enter__(self) -> T:
        if hasattr(self, "_sync_ctx"):
            msg = "Cannot reuse a context manager."
            raise RuntimeError(msg)

        self._sync_ctx = sync_singleton(self.types)
        try:
            return self._sync_ctx.__enter__()
        except BaseException:
            del self._sync_ctx
            raise

    def __exit__(self, *args) -> None:
        try:
            self._sync_ctx.__exit__(*args)
        finally:
            del self._sync_ctx

    async def __aenter__(self) -> T:
        if hasattr(self, "_async_ctx"):
            msg = "Cannot reuse a context manager."
            raise RuntimeError(msg)

        self._async_ctx = async_singleton(self.types)
        try:
            return await self._async_ctx.__aenter__()
        except BaseException:
            del self._async_ctx
            raise

    async def __aexit__(self, *args) -> None:
        try:
            await self._async_ctx.__aexit__(*args)
        finally:
            del self._async_ctx
