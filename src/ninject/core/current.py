from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from contextlib import AbstractContextManager
from types import TracebackType
from typing import TypeVar

from ninject._private.inspect import required
from ninject._private.scope import get_scope_constructor

T = TypeVar("T")


class current(AbstractContextManager[T], AbstractAsyncContextManager[T]):  # noqa: N801
    """A context manager to provide the current value of a dependency."""

    def __init__(self, cls: type[T], default: T = required) -> None:
        try:
            self._scope_provider = get_scope_constructor(cls)
        except RuntimeError:
            if default is required:
                raise
            self._default = default

    def __enter__(self) -> T:
        if hasattr(self, "_default"):
            return self._default
        self._sync_scope = self._scope_provider()
        return self._sync_scope.__enter__()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if hasattr(self, "_sync_scope"):
            self._sync_scope.__exit__(exc_type, exc_value, traceback)
            del self._sync_scope

    async def __aenter__(self) -> T:
        if hasattr(self, "_default"):
            return self._default
        self._async_scope = self._scope_provider()
        return await self._async_scope.__aenter__()

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if hasattr(self, "_async_scope"):
            await self._async_scope.__aexit__(exc_type, exc_value, traceback)
            del self._async_scope
