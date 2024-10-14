from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from contextlib import AbstractContextManager
from typing import TYPE_CHECKING
from typing import ParamSpec
from typing import TypeVar

from pybooster.core._private._shared import async_set_shared_context
from pybooster.core._private._shared import sync_set_shared_context
from pybooster.core._private._utils import normalize_dependency
from pybooster.core._private._utils import undefined

if TYPE_CHECKING:
    from collections.abc import Sequence


P = ParamSpec("P")
R = TypeVar("R")
G = TypeVar("G")


def shared(cls: type[R] | Sequence[type[R]], value: R = undefined) -> _SharedContext[R]:
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
        if hasattr(self, "_sync_reset"):
            msg = "Cannot reuse a context manager."
            raise RuntimeError(msg)
        value, self._sync_reset = sync_set_shared_context(self.types, self.value)
        return value

    def __exit__(self, *args) -> None:
        try:
            self._sync_reset()
        finally:
            del self._sync_reset

    async def __aenter__(self) -> R:
        if hasattr(self, "_async_reset"):
            msg = "Cannot reuse a context manager."
            raise RuntimeError(msg)
        value, self._async_reset = async_set_shared_context(self.types, self.value)
        return value

    async def __aexit__(self, *args) -> None:
        try:
            await self._async_reset()
        finally:
            del self._async_reset
