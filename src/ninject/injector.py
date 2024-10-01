from __future__ import annotations

from contextlib import AsyncExitStack
from contextlib import ExitStack
from functools import wraps
from typing import TYPE_CHECKING
from typing import Any
from typing import Callable
from typing import ParamSpec
from typing import TypeVar

from paramorator import paramorator

from ninject._private.injector import async_update_arguments_by_initializing_dependencies
from ninject._private.injector import setdefault_arguments_with_initialized_dependencies
from ninject._private.injector import sync_update_arguments_by_initializing_dependencies
from ninject._private.utils import get_callable_dependencies

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from collections.abc import Coroutine
    from collections.abc import Iterator
    from collections.abc import Mapping

    from ninject.types import AsyncIteratorCallable
    from ninject.types import IteratorCallable

P = ParamSpec("P")
R = TypeVar("R")


@paramorator
def function(
    func: Callable[P, R],
    *,
    dependencies: Mapping[str, type] | None = None,
) -> Callable[P, R]:
    """Inject dependencies into the given function."""
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
    dependencies: Mapping[str, type] | None = None,
) -> Callable[P, Coroutine[Any, Any, R]]:
    """Inject dependencies into the given coroutine."""
    dependencies = get_callable_dependencies(func, dependencies)

    @wraps(func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
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
    dependencies: Mapping[str, type] | None = None,
) -> IteratorCallable[P, R]:
    """Inject dependencies into the given iterator."""
    dependencies = get_callable_dependencies(func, dependencies)

    @wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> Iterator[R]:
        if not (missing := setdefault_arguments_with_initialized_dependencies(kwargs, dependencies)):
            yield from func(*args, **kwargs)
        with ExitStack() as stack:
            sync_update_arguments_by_initializing_dependencies(stack, kwargs, missing)
            yield from func(*args, **kwargs)

    return wrapper


@paramorator
def asynciterator(
    func: AsyncIteratorCallable[P, R],
    *,
    dependencies: Mapping[str, type] | None = None,
) -> AsyncIteratorCallable[P, R]:
    """Inject dependencies into the given async iterator."""
    dependencies = get_callable_dependencies(func, dependencies)

    @wraps(func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> AsyncIterator[R]:
        if not (missing := setdefault_arguments_with_initialized_dependencies(kwargs, dependencies)):
            async for value in func(*args, **kwargs):
                yield value
        async with AsyncExitStack() as stack:
            await async_update_arguments_by_initializing_dependencies(stack, kwargs, missing)
            async for value in func(*args, **kwargs):
                yield value

    return wrapper
