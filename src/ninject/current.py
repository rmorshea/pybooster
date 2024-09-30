from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from contextlib import AbstractContextManager
from contextlib import ExitStack
from typing import Any
from typing import Literal
from typing import TypeVar

from ninject._private.context import async_update_arguments_by_initializing_dependencies
from ninject._private.context import set_dependency
from ninject._private.context import setdefault_arguments_with_initialized_dependencies
from ninject._private.context import sync_update_arguments_by_initializing_dependencies
from ninject.types import required

T = TypeVar("T")


def current(cls: type[T], *, provide: T = required) -> Current[T]:
    """Get the current value of a dependency."""
    return Current(cls, provide)


class Current(AbstractContextManager[T], AbstractAsyncContextManager[T]):
    """A context manager to provide the current value of a dependency."""

    def __init__(self, cls: type[T], provide: T) -> None:
        """Initialize the context manager.

        Args:
            cls: The class of the dependency.
            provide: The value to set as the current value.
        """
        self.cls = cls
        self.provide = provide

    def __enter__(self) -> T:
        if hasattr(self, "_sync_stack"):
            msg = "Cannot reuse a context manager."
            raise RuntimeError(msg)

        stack = self._sync_stack = ExitStack()

        if self.provide is not required:
            set_dependency(stack, self.cls, self.provide)

        values: dict[Literal["dependency"], T] = {}
        if not (
            missing := setdefault_arguments_with_initialized_dependencies(stack, values, {}, {"dependency": self.cls})
        ):
            return values["dependency"]

        sync_update_arguments_by_initializing_dependencies(stack, values, missing)
        return values["dependency"]

    async def __aenter__(self) -> T:
        if hasattr(self, "_async_stack"):
            msg = "Cannot reuse a context manager."
            raise RuntimeError(msg)

        stack = self._async_stack = ExitStack()

        if self.provide is not required:
            set_dependency(stack, self.cls, self.provide)

        values: dict[Literal["dependency"], T] = {}
        if not (
            missing := setdefault_arguments_with_initialized_dependencies(stack, values, {}, {"dependency": self.cls})
        ):
            return values["dependency"]

        await async_update_arguments_by_initializing_dependencies(stack, values, missing)
        return values["dependency"]

    def __exit__(self, *exc: Any) -> None:
        self._sync_stack.__exit__(*exc)

    async def __aexit__(self, *exc: Any) -> None:
        await self._async_stack.__aexit__(*exc)
