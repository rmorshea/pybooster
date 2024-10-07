from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from contextlib import AbstractContextManager
from contextlib import ExitStack
from typing import Any
from typing import Literal
from typing import TypeVar

from ninject._private._injector import async_update_arguments_by_initializing_dependencies
from ninject._private._injector import setdefault_arguments_with_initialized_dependencies
from ninject._private._injector import sync_update_arguments_by_initializing_dependencies

T = TypeVar("T")


def current(cls: type[T]) -> CurrentContext[T]:
    """Get the current value of a dependency."""
    return CurrentContext(cls)


class CurrentContext(AbstractContextManager[T], AbstractAsyncContextManager[T]):
    """A context manager to provide the current value of a dependency."""

    def __init__(self, cls: type[T]) -> None:
        """Initialize the context manager.

        Args:
            cls: The class of the dependency.
            provide: The value to set as the current value.
        """
        self.cls = cls

    def __enter__(self) -> T:
        if hasattr(self, "_sync_stack"):
            msg = "Cannot reuse a context manager."
            raise RuntimeError(msg)

        values: dict[Literal["dependency"], T] = {}
        if not (missing := setdefault_arguments_with_initialized_dependencies(values, {"dependency": self.cls})):
            return values["dependency"]

        stack = self._sync_stack = ExitStack()

        sync_update_arguments_by_initializing_dependencies(stack, values, missing)
        return values["dependency"]

    async def __aenter__(self) -> T:
        if hasattr(self, "_async_stack"):
            msg = "Cannot reuse a context manager."
            raise RuntimeError(msg)

        values: dict[Literal["dependency"], T] = {}
        if not (missing := setdefault_arguments_with_initialized_dependencies(values, {"dependency": self.cls})):
            return values["dependency"]

        stack = self._async_stack = ExitStack()

        await async_update_arguments_by_initializing_dependencies(stack, values, missing)
        return values["dependency"]

    def __exit__(self, *exc: Any) -> None:
        if hasattr(self, "_sync_stack"):
            try:
                self._sync_stack.__exit__(*exc)
            finally:
                del self._sync_stack

    async def __aexit__(self, *exc: Any) -> None:
        if hasattr(self, "_async_stack"):
            try:
                await self._async_stack.__aexit__(*exc)
            finally:
                del self._async_stack
