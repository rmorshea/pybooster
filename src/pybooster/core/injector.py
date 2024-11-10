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
from typing import cast

from paramorator import paramorator

from pybooster.core._private._injector import async_update_arguments_from_providers_or_fallbacks
from pybooster.core._private._injector import sync_update_arguments_from_providers_or_fallbacks
from pybooster.core._private._injector import update_argument_from_current_values
from pybooster.core._private._utils import FallbackMarker
from pybooster.core._private._utils import get_callable_dependencies
from pybooster.core._private._utils import get_callable_fallbacks
from pybooster.core._private._utils import make_sentinel_value
from pybooster.core._private._utils import normalize_dependency
from pybooster.core._private._utils import undefined

if TYPE_CHECKING:
    from collections.abc import Mapping
    from collections.abc import Sequence

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from collections.abc import Coroutine
    from collections.abc import Iterator
    from collections.abc import Sequence

    from pybooster.types import AsyncIteratorCallable
    from pybooster.types import IteratorCallable
    from pybooster.types import ParamTypes

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
    dependencies: ParamTypes | None = None,
    fallbacks: Mapping[str, Any] | None = None,
) -> Callable[P, R]:
    """Inject dependencies into the given function.

    Args:
        func: The function to inject dependencies into.
        dependencies: The dependencies to inject into the function. Otherwise infered from function signature.
        fallbacks: The values to use for missing dependencies. Otherwise infered from function signature.
    """
    dependencies = get_callable_dependencies(func, dependencies)
    fallbacks = get_callable_fallbacks(func, fallbacks)

    @wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        if not (missing := update_argument_from_current_values(kwargs, dependencies)):
            return func(*args, **kwargs)
        with ExitStack() as stack:
            sync_update_arguments_from_providers_or_fallbacks(stack, kwargs, missing, fallbacks)
            return func(*args, **kwargs)

    return wrapper


@paramorator
def asyncfunction(
    func: Callable[P, Coroutine[Any, Any, R]],
    *,
    dependencies: ParamTypes | None = None,
    fallbacks: Mapping[str, Any] | None = None,
) -> Callable[P, Coroutine[Any, Any, R]]:
    """Inject dependencies into the given coroutine."""
    dependencies = get_callable_dependencies(func, dependencies)
    fallbacks = get_callable_fallbacks(func, fallbacks)

    @wraps(func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:  # type: ignore[reportReturnType]
        if not (missing := update_argument_from_current_values(kwargs, dependencies)):
            return await func(*args, **kwargs)
        async with AsyncExitStack() as stack:
            await async_update_arguments_from_providers_or_fallbacks(stack, kwargs, missing, fallbacks)
            return await func(*args, **kwargs)

    return wrapper


@paramorator
def iterator(
    func: IteratorCallable[P, R],
    *,
    dependencies: ParamTypes | None = None,
    fallbacks: Mapping[str, Any] | None = None,
) -> IteratorCallable[P, R]:
    """Inject dependencies into the given iterator."""
    dependencies = get_callable_dependencies(func, dependencies)
    fallbacks = get_callable_fallbacks(func, fallbacks)

    @wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> Iterator[R]:
        if not (missing := update_argument_from_current_values(kwargs, dependencies)):
            yield from func(*args, **kwargs)
            return
        with ExitStack() as stack:
            sync_update_arguments_from_providers_or_fallbacks(stack, kwargs, missing, fallbacks)
            yield from func(*args, **kwargs)
            return

    return wrapper


@paramorator
def asynciterator(
    func: AsyncIteratorCallable[P, R],
    *,
    dependencies: ParamTypes | None = None,
    fallbacks: Mapping[str, Any] | None = None,
) -> AsyncIteratorCallable[P, R]:
    """Inject dependencies into the given async iterator."""
    dependencies = get_callable_dependencies(func, dependencies)
    fallbacks = get_callable_fallbacks(func, fallbacks)

    @wraps(func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> AsyncIterator[R]:
        if not (missing := update_argument_from_current_values(kwargs, dependencies)):
            async for value in func(*args, **kwargs):
                yield value
            return
        async with AsyncExitStack() as stack:
            await async_update_arguments_from_providers_or_fallbacks(stack, kwargs, missing, fallbacks)
            async for value in func(*args, **kwargs):
                yield value
            return

    return wrapper


@paramorator
def contextmanager(
    func: IteratorCallable[P, R],
    *,
    dependencies: ParamTypes | None = None,
    fallbacks: Mapping[str, Any] | None = None,
) -> Callable[P, AbstractContextManager[R]]:
    """Inject dependencies into the given context manager function."""
    return _contextmanager(iterator(func, dependencies=dependencies, fallbacks=fallbacks))


@paramorator
def asynccontextmanager(
    func: AsyncIteratorCallable[P, R],
    *,
    dependencies: ParamTypes | None = None,
    fallbacks: Mapping[str, Any] | None = None,
) -> Callable[P, AbstractAsyncContextManager[R]]:
    """Inject dependencies into the given async context manager function."""
    return _asynccontextmanager(asynciterator(func, dependencies=dependencies, fallbacks=fallbacks))


def current(cls: type[R], *, fallback: R = undefined) -> _CurrentContext[R]:
    """Get the current value of a dependency."""
    return _CurrentContext(normalize_dependency(cls), fallback)


_StaticKey = Literal["dependency"]


class _CurrentContext(AbstractContextManager[R], AbstractAsyncContextManager[R]):
    """A context manager to provide the current value of a dependency."""

    def __init__(self, types: Sequence[type[R]], fallback: R) -> None:
        self._required_params: dict[_StaticKey, Sequence[type[R]]] = {"dependency": types}
        self._fallback_values: dict[_StaticKey, R] = {"dependency": fallback} if fallback is not undefined else {}

    def __enter__(self) -> R:
        if hasattr(self, "_sync_stack"):
            msg = "Cannot reuse a context manager."
            raise RuntimeError(msg)

        values: dict[_StaticKey, R] = {}
        if not (missing := update_argument_from_current_values(values, self._required_params)):  # type: ignore[reportArgumentType]
            return values["dependency"]

        stack = self._sync_stack = ExitStack()

        sync_update_arguments_from_providers_or_fallbacks(stack, values, missing, self._fallback_values)  # type: ignore[reportArgumentType]
        return values["dependency"]

    async def __aenter__(self) -> R:
        if hasattr(self, "_async_stack"):
            msg = "Cannot reuse a context manager."
            raise RuntimeError(msg)

        values: dict[Literal["dependency"], R] = {}
        if not (missing := update_argument_from_current_values(values, self._required_params)):  # type: ignore[reportArgumentType]
            return values["dependency"]

        stack = self._async_stack = AsyncExitStack()

        await async_update_arguments_from_providers_or_fallbacks(stack, values, missing, self._fallback_values)  # type: ignore[reportArgumentType]
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
