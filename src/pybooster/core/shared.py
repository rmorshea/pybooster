from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from contextlib import AbstractContextManager
from typing import TYPE_CHECKING
from typing import ParamSpec
from typing import TypeVar

from pybooster.core._private._shared import async_shared_context
from pybooster.core._private._shared import sync_shared_context
from pybooster.core._private._utils import normalize_dependency
from pybooster.core._private._utils import undefined

if TYPE_CHECKING:
    from collections.abc import Sequence


P = ParamSpec("P")
R = TypeVar("R")
G = TypeVar("G")


def shared(cls: type[R] | Sequence, value: R = undefined) -> _SharedContext[R]:
    """Declare that a single value should be shared across all injections of a dependency.

    Args:
        cls: The dependency to share.
        value: The value to share. If not provided, the dependency will be resolved.
    """
    return _SharedContext(normalize_dependency(cls), value=value)


class _SharedContext(AbstractContextManager[R], AbstractAsyncContextManager[R]):
    """A context manager to declare a shared instance of a dependency."""

    def __init__(self, types: Sequence[type[R]], value: R) -> None:
        self.types = types
        self.value = value

    def __enter__(self) -> R:
        if hasattr(self, "_sync_ctx"):
            msg = "Cannot reuse a context manager."
            raise RuntimeError(msg)

        self._sync_ctx = sync_shared_context(self.types, self.value)
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

    async def __aenter__(self) -> R:
        if hasattr(self, "_async_ctx"):
            msg = "Cannot reuse a context manager."
            raise RuntimeError(msg)

        self._async_ctx = async_shared_context(self.types, self.value)
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
