from __future__ import annotations

from collections.abc import Mapping
from contextlib import AbstractAsyncContextManager
from contextlib import AbstractContextManager
from contextlib import asynccontextmanager as _asynccontextmanager
from contextlib import contextmanager as _contextmanager
from functools import wraps
from typing import TYPE_CHECKING
from typing import Any
from typing import ParamSpec
from typing import TypeVar
from typing import cast

from paramorator import paramorator

from pybooster._private._injector import _CURRENT_VALUES
from pybooster._private._injector import async_inject_into_params
from pybooster._private._injector import sync_inject_into_params
from pybooster._private._utils import AsyncFastStack
from pybooster._private._utils import FastStack
from pybooster._private._utils import get_required_parameters
from pybooster._private._utils import make_sentinel_value
from pybooster.types import Hint

if TYPE_CHECKING:
    from collections.abc import Callable

    from pybooster.types import HintSeq

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
    requires: HintMap | HintSeq | None = None,
    shared: bool = False,
) -> Callable[P, R]:
    """Inject dependencies into the given function.

    Args:
        func: The function to inject dependencies into.
        requires: The parameters and dependencies to inject. Otherwise infered from signature.
        shared: Whether injected values should be shared for the duration of any calls.
    """
    requires = get_required_parameters(func, requires)

    @wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        stack = FastStack()
        try:
            sync_inject_into_params(stack, kwargs, requires, keep_current_values=shared)
            return func(*args, **kwargs)
        finally:
            stack.close()

    return wrapper


@paramorator
def asyncfunction(
    func: Callable[P, Coroutine[Any, Any, R]],
    *,
    requires: HintMap | HintSeq | None = None,
    shared: bool = False,
) -> Callable[P, Coroutine[Any, Any, R]]:
    """Inject dependencies into the given coroutine.

    Args:
        func: The function to inject dependencies into.
        requires: The parameters and dependencies to inject. Otherwise infered from signature.
        shared: Whether injected values should be shared for the duration of any calls.
    """
    requires = get_required_parameters(func, requires)

    @wraps(func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:  # type: ignore[reportReturnType]
        stack = AsyncFastStack()
        try:
            await async_inject_into_params(stack, kwargs, requires, keep_current_values=shared)
            return await func(*args, **kwargs)
        finally:
            await stack.aclose()

    return wrapper


@paramorator
def iterator(
    func: IteratorCallable[P, R],
    *,
    requires: HintMap | HintSeq | None = None,
    shared: bool = False,
) -> IteratorCallable[P, R]:
    """Inject dependencies into the given iterator.

    Args:
        func: The function to inject dependencies into.
        requires: The parameters and dependencies to inject. Otherwise infered from signature.
        shared: Whether injected values should be shared for the duration of any calls.
    """
    requires = get_required_parameters(func, requires)

    @wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> Iterator[R]:
        stack = FastStack()
        try:
            sync_inject_into_params(stack, kwargs, requires, keep_current_values=shared)
            yield from func(*args, **kwargs)
        finally:
            stack.close()

    return wrapper


@paramorator
def asynciterator(
    func: AsyncIteratorCallable[P, R],
    *,
    requires: HintMap | HintSeq | None = None,
    shared: bool = False,
) -> AsyncIteratorCallable[P, R]:
    """Inject dependencies into the given async iterator.

    Args:
        func: The function to inject dependencies into.
        requires: The parameters and dependencies to inject. Otherwise infered from signature.
        shared: Whether injected values should be shared for the duration of any calls.
    """
    requires = get_required_parameters(func, requires)

    @wraps(func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> AsyncIterator[R]:
        stack = AsyncFastStack()
        try:
            await async_inject_into_params(stack, kwargs, requires, keep_current_values=shared)
            async for value in func(*args, **kwargs):
                yield value
        finally:
            await stack.aclose()

    return wrapper


@paramorator
def contextmanager(
    func: IteratorCallable[P, R],
    *,
    requires: HintMap | HintSeq | None = None,
    shared: bool = False,
) -> Callable[P, AbstractContextManager[R]]:
    """Inject dependencies into the given context manager function.

    Args:
        func: The function to inject dependencies into.
        requires: The parameters and dependencies to inject. Otherwise infered from signature.
        shared: Whether injected values should be shared for the duration of the context.
    """
    return _contextmanager(iterator(func, requires=requires, shared=shared))


@paramorator
def asynccontextmanager(
    func: AsyncIteratorCallable[P, R],
    *,
    requires: HintMap | HintSeq | None = None,
    shared: bool = False,
) -> Callable[P, AbstractAsyncContextManager[R]]:
    """Inject dependencies into the given async context manager function.

    Args:
        func: The function to inject dependencies into.
        requires: The parameters and dependencies to inject. Otherwise infered from signature.
        shared: Whether injected values should be shared for the duration of the context.
    """
    return _asynccontextmanager(asynciterator(func, requires=requires, shared=shared))


def shared(*args: Hint | tuple[Hint, Any]) -> _SharedContext:
    """Share the values for a set of dependencies for the duration of a context."""
    param_vals: dict[str, Any] = {}
    param_deps: dict[str, Hint] = {}
    for index, arg in enumerate(args):
        key = f"__{index}"
        match arg:
            case [cls, val]:
                param_vals[key] = val
                param_deps[key] = cls
            case cls:
                param_deps[key] = cls
    return _SharedContext(param_vals, param_deps)


def current_values() -> CurrentValues:
    """Get a mapping from dependency types to their current values."""
    return cast("CurrentValues", dict(_CURRENT_VALUES.get()))


class CurrentValues(Mapping[Hint, Any]):
    """A mapping from dependency types to their current values."""

    def __getitem__(self, key: type[R]) -> R: ...
    def get(self, key: type[R], default: R = ...) -> R: ...  # noqa: D102


class _SharedContext(
    AbstractContextManager[CurrentValues], AbstractAsyncContextManager[CurrentValues]
):
    def __init__(
        self,
        param_vals: dict[str, Any],
        param_deps: dict[str, type],
    ) -> None:
        self._param_vals = param_vals
        self._param_deps = param_deps

    def __enter__(self) -> CurrentValues:
        if hasattr(self, "_sync_stack"):
            msg = "Cannot reuse a context manager."
            raise RuntimeError(msg)
        self._sync_stack = FastStack()
        params = self._param_vals.copy()
        sync_inject_into_params(
            self._sync_stack,
            params,
            self._param_deps,
            keep_current_values=True,
        )
        return cast("CurrentValues", {self._param_deps[k]: v for k, v in params.items()})

    def __exit__(self, *_: Any) -> None:
        try:
            self._sync_stack.close()
        finally:
            del self._sync_stack

    async def __aenter__(self) -> CurrentValues:
        if hasattr(self, "_async_stack"):
            msg = "Cannot reuse a context manager."
            raise RuntimeError(msg)
        self._async_stack = AsyncFastStack()
        params = self._param_vals.copy()
        await async_inject_into_params(
            self._async_stack,
            params,
            self._param_deps,
            keep_current_values=True,
        )
        return cast("CurrentValues", {self._param_deps[k]: v for k, v in params.items()})

    async def __aexit__(self, *exc: Any) -> None:
        try:
            await self._async_stack.aclose()
        finally:
            del self._async_stack
