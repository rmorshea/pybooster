from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from contextlib import AbstractContextManager
from contextlib import AsyncExitStack
from contextlib import ExitStack
from contextlib import asynccontextmanager as _asynccontextmanager
from contextlib import contextmanager as _contextmanager
from functools import wraps
from typing import TYPE_CHECKING
from typing import Any
from typing import Callable
from typing import Literal
from typing import ParamSpec
from typing import TypeVar

from paramorator import paramorator

from pybooster.core._private._injector import async_set_current_values
from pybooster.core._private._injector import async_update_arguments_by_initializing_dependencies
from pybooster.core._private._injector import setdefault_arguments_with_initialized_dependencies
from pybooster.core._private._injector import sync_set_current_values
from pybooster.core._private._injector import sync_update_arguments_by_initializing_dependencies
from pybooster.core._private._utils import get_callable_dependencies
from pybooster.core._private._utils import normalize_dependency

if TYPE_CHECKING:
    from collections.abc import Sequence

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from collections.abc import Coroutine
    from collections.abc import Iterator
    from collections.abc import Sequence

    from pybooster.core.types import AsyncIteratorCallable
    from pybooster.core.types import Dependencies
    from pybooster.core.types import IteratorCallable

P = ParamSpec("P")
R = TypeVar("R")


@paramorator
def function(
    func: Callable[P, R],
    *,
    dependencies: Dependencies | None = None,
) -> Callable[P, R]:
    """Inject dependencies into the given function.

    Args:
        func: The function to inject dependencies into.
        dependencies: The dependencies to inject into the function.
    """
    dependencies = get_callable_dependencies(func, dependencies)

    @wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        if not (missing := setdefault_arguments_with_initialized_dependencies(kwargs, dependencies)):
            return func(*args, **kwargs)
        with ExitStack() as stack:
            sync_update_arguments_by_initializing_dependencies(stack, kwargs, missing)
            return func(*args, **kwargs)

    return wrapper


@paramorator
def asyncfunction(
    func: Callable[P, Coroutine[Any, Any, R]],
    *,
    dependencies: Dependencies | None = None,
) -> Callable[P, Coroutine[Any, Any, R]]:
    """Inject dependencies into the given coroutine."""
    dependencies = get_callable_dependencies(func, dependencies)

    @wraps(func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:  # type: ignore[reportReturnType]
        if not (missing := setdefault_arguments_with_initialized_dependencies(kwargs, dependencies)):
            return await func(*args, **kwargs)
        async with AsyncExitStack() as stack:
            await async_update_arguments_by_initializing_dependencies(stack, kwargs, missing)
            return await func(*args, **kwargs)

    return wrapper


@paramorator
def iterator(
    func: IteratorCallable[P, R],
    *,
    dependencies: Dependencies | None = None,
) -> IteratorCallable[P, R]:
    """Inject dependencies into the given iterator."""
    dependencies = get_callable_dependencies(func, dependencies)

    @wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> Iterator[R]:
        try:
            if not (missing := setdefault_arguments_with_initialized_dependencies(kwargs, dependencies)):
                yield from func(*args, **kwargs)
                return
            with ExitStack() as stack:
                sync_update_arguments_by_initializing_dependencies(stack, kwargs, missing)
                yield from func(*args, **kwargs)
                return
        except StopIteration as e:
            return e.value  # noqa: B901

    return wrapper


@paramorator
def asynciterator(
    func: AsyncIteratorCallable[P, R],
    *,
    dependencies: Dependencies | None = None,
) -> AsyncIteratorCallable[P, R]:
    """Inject dependencies into the given async iterator."""
    dependencies = get_callable_dependencies(func, dependencies)

    @wraps(func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> AsyncIterator[R]:
        if not (missing := setdefault_arguments_with_initialized_dependencies(kwargs, dependencies)):
            async for value in func(*args, **kwargs):
                yield value
            return
        async with AsyncExitStack() as stack:
            await async_update_arguments_by_initializing_dependencies(stack, kwargs, missing)
            async for value in func(*args, **kwargs):
                yield value
            return

    return wrapper


@paramorator
def contextmanager(
    func: IteratorCallable[P, R],
    *,
    dependencies: Dependencies | None = None,
) -> Callable[P, AbstractContextManager[R]]:
    """Inject dependencies into the given context manager function."""
    return _contextmanager(iterator(func, dependencies=dependencies))


@paramorator
def asynccontextmanager(
    func: AsyncIteratorCallable[P, R],
    *,
    dependencies: Dependencies | None = None,
) -> Callable[P, AbstractAsyncContextManager[R]]:
    """Inject dependencies into the given async context manager function."""
    return _asynccontextmanager(asynciterator(func, dependencies=dependencies))


def current(cls: type[R]) -> _CurrentContext[R]:
    """Get the current value of a dependency."""
    return _CurrentContext(normalize_dependency(cls))


class _CurrentContext(AbstractContextManager[R], AbstractAsyncContextManager[R]):
    """A context manager to provide the current value of a dependency."""

    def __init__(self, types: Sequence[type[R]]) -> None:
        self.types = types

    def __enter__(self) -> R:
        if hasattr(self, "_sync_stack"):
            msg = "Cannot reuse a context manager."
            raise RuntimeError(msg)

        values: dict[Literal["dependency"], R] = {}
        if not (missing := setdefault_arguments_with_initialized_dependencies(values, {"dependency": self.types})):  # type: ignore[reportArgumentType]
            return values["dependency"]

        stack = self._sync_stack = ExitStack()

        sync_update_arguments_by_initializing_dependencies(stack, values, missing)  # type: ignore[reportArgumentType]
        return values["dependency"]

    async def __aenter__(self) -> R:
        if hasattr(self, "_async_stack"):
            msg = "Cannot reuse a context manager."
            raise RuntimeError(msg)

        values: dict[Literal["dependency"], R] = {}
        if not (missing := setdefault_arguments_with_initialized_dependencies(values, {"dependency": self.types})):  # type: ignore[reportArgumentType]
            return values["dependency"]

        stack = self._async_stack = AsyncExitStack()

        await async_update_arguments_by_initializing_dependencies(stack, values, missing)  # type: ignore[reportArgumentType]
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


def shared(cls: type[R] | Sequence[type[R]]) -> _SharedContext[R]:
    """Declare that a single value should be shared across all injections of a dependency.

    Args:
        cls: The dependency to share.
    """
    return _SharedContext(normalize_dependency(cls))


class _SharedContext(AbstractContextManager[R], AbstractAsyncContextManager[R]):
    """A context manager to declare a shared instance of a dependency."""

    def __init__(self, types: Sequence[type[R]]) -> None:
        self.types = types

    def __enter__(self) -> R:
        if hasattr(self, "_sync_reset"):
            msg = "Cannot reuse a context manager."
            raise RuntimeError(msg)
        value, self._sync_reset = sync_set_current_values(self.types)
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
        value, self._async_reset = await async_set_current_values(self.types)
        return value

    async def __aexit__(self, *args) -> None:
        try:
            await self._async_reset()
        finally:
            del self._async_reset
