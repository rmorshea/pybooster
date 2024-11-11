from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from contextlib import AbstractContextManager
from contextlib import asynccontextmanager as _asynccontextmanager
from contextlib import contextmanager as _contextmanager
from functools import wraps
from typing import TYPE_CHECKING
from typing import Any
from typing import Literal
from typing import ParamSpec
from typing import TypeVar
from typing import cast

from paramorator import paramorator

from pybooster.core._private._injector import async_inject_keywords
from pybooster.core._private._injector import sync_inject_keywords
from pybooster.core._private._utils import AsyncFastStack
from pybooster.core._private._utils import FallbackMarker
from pybooster.core._private._utils import FastStack
from pybooster.core._private._utils import get_fallback_parameters
from pybooster.core._private._utils import get_required_parameters
from pybooster.core._private._utils import make_sentinel_value
from pybooster.core._private._utils import undefined

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


class Fallback:
    """A sentinel object used to indicate that a dependency should fallback to its default."""

    def __getitem__(self, value: R) -> R:
        return cast(R, FallbackMarker(value))


fallback = Fallback()
"""Indicate that a dependency should fallback to its default by using `fallback[default]`."""
del Fallback


@paramorator
def function(
    func: Callable[P, R],
    *,
    dependencies: HintMap | None = None,
    fallbacks: Mapping[str, Any] | None = None,
) -> Callable[P, R]:
    """Inject dependencies into the given function.

    Args:
        func: The function to inject dependencies into.
        dependencies: The dependencies to inject into the function. Otherwise infered from function signature.
        fallbacks: The values to use for missing dependencies. Otherwise infered from function signature.
    """
    required_params = get_required_parameters(func, dependencies)
    fallback_values = get_fallback_parameters(func, fallbacks)

    @wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        stack = FastStack()
        try:
            sync_inject_keywords(stack, kwargs, required_params, fallback_values)
            return func(*args, **kwargs)
        finally:
            stack.close()

    return wrapper


@paramorator
def asyncfunction(
    func: Callable[P, Coroutine[Any, Any, R]],
    *,
    dependencies: HintMap | None = None,
    fallbacks: Mapping[str, Any] | None = None,
) -> Callable[P, Coroutine[Any, Any, R]]:
    """Inject dependencies into the given coroutine."""
    required_params = get_required_parameters(func, dependencies)
    fallback_values = get_fallback_parameters(func, fallbacks)

    @wraps(func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:  # type: ignore[reportReturnType]
        stack = AsyncFastStack()
        try:
            await async_inject_keywords(stack, kwargs, required_params, fallback_values)
            return await func(*args, **kwargs)
        finally:
            await stack.aclose()

    return wrapper


@paramorator
def iterator(
    func: IteratorCallable[P, R],
    *,
    dependencies: HintMap | None = None,
    fallbacks: Mapping[str, Any] | None = None,
) -> IteratorCallable[P, R]:
    """Inject dependencies into the given iterator."""
    required_params = get_required_parameters(func, dependencies)
    fallback_values = get_fallback_parameters(func, fallbacks)

    @wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> Iterator[R]:
        stack = FastStack()
        try:
            sync_inject_keywords(stack, kwargs, required_params, fallback_values)
            yield from func(*args, **kwargs)
        finally:
            stack.close()

    return wrapper


@paramorator
def asynciterator(
    func: AsyncIteratorCallable[P, R],
    *,
    dependencies: HintMap | None = None,
    fallbacks: Mapping[str, Any] | None = None,
) -> AsyncIteratorCallable[P, R]:
    """Inject dependencies into the given async iterator."""
    required_params = get_required_parameters(func, dependencies)
    fallback_values = get_fallback_parameters(func, fallbacks)

    @wraps(func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> AsyncIterator[R]:
        stack = AsyncFastStack()
        try:
            await async_inject_keywords(stack, kwargs, required_params, fallback_values)
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
    fallbacks: Mapping[str, Any] | None = None,
) -> Callable[P, AbstractContextManager[R]]:
    """Inject dependencies into the given context manager function."""
    return _contextmanager(iterator(func, dependencies=dependencies, fallbacks=fallbacks))


@paramorator
def asynccontextmanager(
    func: AsyncIteratorCallable[P, R],
    *,
    dependencies: HintMap | None = None,
    fallbacks: Mapping[str, Any] | None = None,
) -> Callable[P, AbstractAsyncContextManager[R]]:
    """Inject dependencies into the given async context manager function."""
    return _asynccontextmanager(asynciterator(func, dependencies=dependencies, fallbacks=fallbacks))


def current(cls: type[R], *, fallback: R = undefined) -> _CurrentContext[R]:
    """Get the current value of a dependency."""
    return _CurrentContext(cls, fallback)


_StaticKey = Literal["dependency"]


class _CurrentContext(AbstractContextManager[R], AbstractAsyncContextManager[R]):
    """A context manager to provide the current value of a dependency."""

    def __init__(self, cls: type[R], fallback: R) -> None:
        self._required_params: dict[_StaticKey, type[R]] = {"dependency": cls}
        self._fallback_values: dict[_StaticKey, R] = {"dependency": fallback} if fallback is not undefined else {}

    def __enter__(self) -> R:
        if hasattr(self, "_sync_stack"):
            msg = "Cannot reuse a context manager."
            raise RuntimeError(msg)

        self._sync_stack = FastStack()
        values: dict[_StaticKey, R] = {}
        sync_inject_keywords(
            self._sync_stack,
            values,
            self._required_params,
            self._fallback_values,
        )
        return values["dependency"]

    def __exit__(self, *_: Any) -> None:
        if hasattr(self, "_sync_stack"):
            try:
                self._sync_stack.close()
            finally:
                del self._sync_stack

    async def __aenter__(self) -> R:
        if hasattr(self, "_async_stack"):
            msg = "Cannot reuse a context manager."
            raise RuntimeError(msg)

        self._async_stack = AsyncFastStack()
        values: dict[_StaticKey, R] = {}
        await async_inject_keywords(
            self._async_stack,
            values,
            self._required_params,
            self._fallback_values,
        )
        return values["dependency"]

    async def __aexit__(self, *exc: Any) -> None:
        if hasattr(self, "_async_stack"):
            try:
                await self._async_stack.aclose()
            finally:
                del self._async_stack
