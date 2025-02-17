from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from contextlib import AbstractContextManager
from contextlib import asynccontextmanager as _asynccontextmanager
from contextlib import contextmanager as _contextmanager
from functools import wraps
from typing import TYPE_CHECKING
from typing import Any
from typing import ParamSpec

from paramorator import paramorator
from typing_extensions import TypeVar

from pybooster._private._injector import async_inject_into_params
from pybooster._private._injector import sync_inject_into_params
from pybooster._private._utils import AsyncFastStack
from pybooster._private._utils import FastStack
from pybooster._private._utils import get_required_parameters
from pybooster._private._utils import make_sentinel_value

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
N = TypeVar("N", default=None)


required = make_sentinel_value(__name__, "required")
"""A sentinel object used to indicate that a dependency is required.

Refer to the [core concepts](../../concepts.md#injectors) for more information.
"""


@paramorator
def function(
    func: Callable[P, R],
    *,
    requires: HintMap | HintSeq | None = None,
    scope: bool = False,
) -> Callable[P, R]:
    """Inject dependencies into the given function.

    Refer to the [core concepts](../../concepts.md#injectors) for more information.

    Args:
        func: The function to inject dependencies into.
        requires: The parameters and dependencies to inject. Otherwise infered from signature.
        scope: Whether injected values should be shared for the duration of any calls.
    """
    requires = get_required_parameters(func, requires)

    @wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        stack = FastStack()
        try:
            sync_inject_into_params(stack, kwargs, requires, keep_current_values=scope)
            return func(*args, **kwargs)
        finally:
            stack.close()

    return wrapper


@paramorator
def asyncfunction(
    func: Callable[P, Coroutine[Any, Any, R]],
    *,
    requires: HintMap | HintSeq | None = None,
    scope: bool = False,
) -> Callable[P, Coroutine[Any, Any, R]]:
    """Inject dependencies into the given coroutine.

    Refer to the [core concepts](../../concepts.md#injectors) for more information.

    Args:
        func: The function to inject dependencies into.
        requires: The parameters and dependencies to inject. Otherwise infered from signature.
        scope: Whether injected values should be shared for the duration of any calls.
    """
    requires = get_required_parameters(func, requires)

    @wraps(func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:  # type: ignore[reportReturnType]
        stack = AsyncFastStack()
        try:
            await async_inject_into_params(stack, kwargs, requires, keep_current_values=scope)
            return await func(*args, **kwargs)
        finally:
            await stack.aclose()

    return wrapper


@paramorator
def iterator(
    func: IteratorCallable[P, R],
    *,
    requires: HintMap | HintSeq | None = None,
    scope: bool = False,
) -> IteratorCallable[P, R]:
    """Inject dependencies into the given iterator.

    Refer to the [core concepts](../../concepts.md#injectors) for more information.

    Args:
        func: The function to inject dependencies into.
        requires: The parameters and dependencies to inject. Otherwise infered from signature.
        scope: Whether injected values should be shared for the duration of any calls.
    """
    requires = get_required_parameters(func, requires)

    @wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> Iterator[R]:
        stack = FastStack()
        try:
            sync_inject_into_params(stack, kwargs, requires, keep_current_values=scope)
            yield from func(*args, **kwargs)
        finally:
            stack.close()

    return wrapper


@paramorator
def asynciterator(
    func: AsyncIteratorCallable[P, R],
    *,
    requires: HintMap | HintSeq | None = None,
    scope: bool = False,
) -> AsyncIteratorCallable[P, R]:
    """Inject dependencies into the given async iterator.

    Refer to the [core concepts](../../concepts.md#injectors) for more information.

    Args:
        func: The function to inject dependencies into.
        requires: The parameters and dependencies to inject. Otherwise infered from signature.
        scope: Whether injected values should be shared for the duration of any calls.
    """
    requires = get_required_parameters(func, requires)

    @wraps(func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> AsyncIterator[R]:
        stack = AsyncFastStack()
        try:
            await async_inject_into_params(stack, kwargs, requires, keep_current_values=scope)
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
    scope: bool = False,
) -> Callable[P, AbstractContextManager[R]]:
    """Inject dependencies into the given context manager function.

    Refer to the [core concepts](../../concepts.md#injectors) for more information.

    Args:
        func: The function to inject dependencies into.
        requires: The parameters and dependencies to inject. Otherwise infered from signature.
        scope: Whether injected values should be shared for the duration of the context.
    """
    return _contextmanager(iterator(func, requires=requires, scope=scope))


@paramorator
def asynccontextmanager(
    func: AsyncIteratorCallable[P, R],
    *,
    requires: HintMap | HintSeq | None = None,
    scope: bool = False,
) -> Callable[P, AbstractAsyncContextManager[R]]:
    """Inject dependencies into the given async context manager function.

    Refer to the [core concepts](../../concepts.md#injectors) for more information.

    Args:
        func: The function to inject dependencies into.
        requires: The parameters and dependencies to inject. Otherwise infered from signature.
        scope: Whether injected values should be shared for the duration of the context.
    """
    return _asynccontextmanager(asynciterator(func, requires=requires, scope=scope))
