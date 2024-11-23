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

from pybooster._private._injector import async_inject_known_params
from pybooster._private._injector import sync_inject_known_params
from pybooster._private._utils import AsyncFastStack
from pybooster._private._utils import FastStack
from pybooster._private._utils import get_required_parameters
from pybooster._private._utils import make_sentinel_value

if TYPE_CHECKING:
    from collections.abc import Callable
    from collections.abc import Collection
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
        dependencies: The parameters and dependencies to inject. Otherwise infered from signature.
    """
    required_params = get_required_parameters(func, dependencies)

    @wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        stack = FastStack()
        try:
            sync_inject_known_params(stack, required_params, kwargs)
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
    """Inject dependencies into the given coroutine.

    Args:
        func: The function to inject dependencies into.
        dependencies: The parameters and dependencies to inject. Otherwise infered from signature.
    """
    required_params = get_required_parameters(func, dependencies)

    @wraps(func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:  # type: ignore[reportReturnType]
        stack = AsyncFastStack()
        try:
            await async_inject_known_params(stack, required_params, kwargs)
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
    """Inject dependencies into the given iterator.

    Args:
        func: The function to inject dependencies into.
        dependencies: The parameters and dependencies to inject. Otherwise infered from signature.
    """
    required_params = get_required_parameters(func, dependencies)

    @wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> Iterator[R]:
        stack = FastStack()
        try:
            sync_inject_known_params(stack, required_params, kwargs)
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
    """Inject dependencies into the given async iterator.

    Args:
        func: The function to inject dependencies into.
        dependencies: The parameters and dependencies to inject. Otherwise infered from signature.
    """
    required_params = get_required_parameters(func, dependencies)

    @wraps(func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> AsyncIterator[R]:
        stack = AsyncFastStack()
        try:
            await async_inject_known_params(stack, required_params, kwargs)
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
    """Inject dependencies into the given context manager function.

    Args:
        func: The function to inject dependencies into.
        dependencies: The parameters and dependencies to inject. Otherwise infered from signature.
    """
    return _contextmanager(iterator(func, dependencies=dependencies))


@paramorator
def asynccontextmanager(
    func: AsyncIteratorCallable[P, R],
    *,
    dependencies: HintMap | None = None,
) -> Callable[P, AbstractAsyncContextManager[R]]:
    """Inject dependencies into the given async context manager function.

    Args:
        func: The function to inject dependencies into.
        dependencies: The parameters and dependencies to inject. Otherwise infered from signature.
    """
    return _asynccontextmanager(asynciterator(func, dependencies=dependencies))


def shared(
    *,
    overrides: Mapping[type[R], R] | None = None,
    dependencies: Collection[type[R]] | None = None,
) -> _SharedContext[R]:
    """Declare that a set of dependency values should be shared for the duration of a context.

    Args:
        overrides: Declare the exact values for each dependency that should be shared.
        dependencies: Declare the dependency types that should be shared.
    """
    return _SharedContext(overrides or {}, dependencies or [])


class _SharedContext(
    AbstractContextManager[dict[type[R], R]],
    AbstractAsyncContextManager[dict[type[R], R]],
):
    def __init__(
        self,
        overrides: Mapping[type[R], R],
        dependencies: Collection[type[R]],
    ) -> None:
        self._known_params: dict[str, R] = {}
        self._required_params: dict[str, type[R]] = {}
        for i, cls in enumerate(overrides.keys() | dependencies):
            key = f"key_{i}"
            self._required_params[key] = cls
            if cls in overrides:
                self._known_params[key] = overrides[cls]

    def __enter__(self) -> dict[type[R], R]:
        if hasattr(self, "_sync_stack"):
            msg = "Cannot reuse a context manager."
            raise RuntimeError(msg)
        self._sync_stack = FastStack()
        values: dict[str, R] = self._known_params.copy()
        sync_inject_known_params(
            self._sync_stack,
            self._required_params,
            values,
            keep_current_values=True,
        )
        return {self._required_params[k]: v for k, v in values.items()}

    def __exit__(self, *_: Any) -> None:
        try:
            self._sync_stack.close()
        finally:
            del self._sync_stack

    async def __aenter__(self) -> dict[type[R], R]:
        if hasattr(self, "_async_stack"):
            msg = "Cannot reuse a context manager."
            raise RuntimeError(msg)
        self._async_stack = AsyncFastStack()
        values: dict[str, R] = self._known_params.copy()
        await async_inject_known_params(
            self._async_stack,
            self._required_params,
            values,
            keep_current_values=True,
        )
        return {self._required_params[k]: v for k, v in values.items()}

    async def __aexit__(self, *exc: Any) -> None:
        try:
            await self._async_stack.aclose()
        finally:
            del self._async_stack
