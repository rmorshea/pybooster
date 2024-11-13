from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from contextlib import AbstractContextManager
from contextlib import asynccontextmanager as _asynccontextmanager
from contextlib import contextmanager as _contextmanager
from functools import wraps
from typing import TYPE_CHECKING
from typing import Any
from typing import ParamSpec
from typing import TypeVar

from paramorator import paramorator

from pybooster._private._injector import async_inject_keywords
from pybooster._private._injector import overwrite_values
from pybooster._private._injector import sync_inject_keywords
from pybooster._private._utils import AsyncFastStack
from pybooster._private._utils import FastStack
from pybooster._private._utils import get_required_parameters
from pybooster._private._utils import make_sentinel_value

if TYPE_CHECKING:
    from collections.abc import Callable
    from collections.abc import Mapping

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from collections.abc import Coroutine
    from collections.abc import Iterator

    from pybooster.types import AsyncIteratorCallable
    from pybooster.types import HintMap
    from pybooster.types import IteratorCallable

P = ParamSpec("P")
R = TypeVar("R")


required = make_sentinel_value(__name__, "required")
"""A sentinel object used to indicate that a dependency is required."""


@paramorator
def function(
    func: Callable[P, R],
    *,
    dependencies: HintMap | None = None,
) -> Callable[P, R]:
    """Inject dependencies into the given function.

    Args:
        func: The function to inject dependencies into.
        dependencies: The dependencies to inject into the function. Otherwise infered from function signature.
    """
    required_params = get_required_parameters(func, dependencies)

    @wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        stack = FastStack()
        try:
            sync_inject_keywords(stack, required_params, kwargs)
            return func(*args, **kwargs)
        finally:
            stack.close()

    return wrapper


@paramorator
def asyncfunction(
    func: Callable[P, Coroutine[Any, Any, R]],
    *,
    dependencies: HintMap | None = None,
) -> Callable[P, Coroutine[Any, Any, R]]:
    """Inject dependencies into the given coroutine."""
    required_params = get_required_parameters(func, dependencies)

    @wraps(func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:  # type: ignore[reportReturnType]
        stack = AsyncFastStack()
        try:
            await async_inject_keywords(stack, required_params, kwargs)
            return await func(*args, **kwargs)
        finally:
            await stack.aclose()

    return wrapper


@paramorator
def iterator(
    func: IteratorCallable[P, R],
    *,
    dependencies: HintMap | None = None,
) -> IteratorCallable[P, R]:
    """Inject dependencies into the given iterator."""
    required_params = get_required_parameters(func, dependencies)

    @wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> Iterator[R]:
        stack = FastStack()
        try:
            sync_inject_keywords(stack, required_params, kwargs)
            yield from func(*args, **kwargs)
        finally:
            stack.close()

    return wrapper


@paramorator
def asynciterator(
    func: AsyncIteratorCallable[P, R],
    *,
    dependencies: HintMap | None = None,
) -> AsyncIteratorCallable[P, R]:
    """Inject dependencies into the given async iterator."""
    required_params = get_required_parameters(func, dependencies)

    @wraps(func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> AsyncIterator[R]:
        stack = AsyncFastStack()
        try:
            await async_inject_keywords(stack, required_params, kwargs)
            async for value in func(*args, **kwargs):
                yield value
        finally:
            await stack.aclose()

    return wrapper


@paramorator
def contextmanager(
    func: IteratorCallable[P, R],
    *,
    dependencies: HintMap | None = None,
) -> Callable[P, AbstractContextManager[R]]:
    """Inject dependencies into the given context manager function."""
    return _contextmanager(iterator(func, dependencies=dependencies))


@paramorator
def asynccontextmanager(
    func: AsyncIteratorCallable[P, R],
    *,
    dependencies: HintMap | None = None,
) -> Callable[P, AbstractAsyncContextManager[R]]:
    """Inject dependencies into the given async context manager function."""
    return _asynccontextmanager(asynciterator(func, dependencies=dependencies))


def overwrite(values: Mapping[type, Any]) -> _OverwriteContext:
    """Overwrite the current values of the given dependencies."""
    return _OverwriteContext(values)


class _OverwriteContext(AbstractContextManager[None]):

    def __init__(self, values: Mapping[type, Any]) -> None:
        self._values = values

    def __enter__(self) -> None:
        if hasattr(self, "_reset"):
            msg = "Cannot reuse a context manager."
            raise RuntimeError(msg)
        self._reset = overwrite_values(self._values)

    def __exit__(self, *_: Any) -> None:
        try:
            self._reset()
        finally:
            del self._reset


def current(cls: type[R]) -> _CurrentContext[R]:
    """Get the current value of a dependency."""
    return _CurrentContext(cls)


_KEY = ""


class _CurrentContext(AbstractContextManager[R], AbstractAsyncContextManager[R]):
    """A context manager to provide the current value of a dependency."""

    def __init__(self, cls: type[R]) -> None:
        self._required_params: dict[str, type[R]] = {_KEY: cls}

    def __enter__(self) -> R:
        if hasattr(self, "_sync_stack"):
            msg = "Cannot reuse a context manager."
            raise RuntimeError(msg)
        self._sync_stack = FastStack()
        values = {}
        sync_inject_keywords(self._sync_stack, self._required_params, values)
        return values[_KEY]

    def __exit__(self, *_: Any) -> None:
        try:
            self._sync_stack.close()
        finally:
            del self._sync_stack

    async def __aenter__(self) -> R:
        if hasattr(self, "_async_stack"):
            msg = "Cannot reuse a context manager."
            raise RuntimeError(msg)
        self._async_stack = AsyncFastStack()
        values = {}
        await async_inject_keywords(self._async_stack, self._required_params, values)
        return values[_KEY]

    async def __aexit__(self, *exc: Any) -> None:
        try:
            await self._async_stack.aclose()
        finally:
            del self._async_stack
