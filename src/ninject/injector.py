from __future__ import annotations

from contextlib import AsyncExitStack
from contextlib import ExitStack
from functools import wraps
from typing import TYPE_CHECKING
from typing import Any
from typing import Callable
from typing import ParamSpec
from typing import TypeVar

from ninject._private.context import async_update_arguments_by_initializing_dependencies
from ninject._private.context import setdefault_arguments_with_initialized_dependencies
from ninject._private.context import sync_update_arguments_by_initializing_dependencies
from ninject._private.utils import decorator
from ninject._private.utils import get_dependencies
from ninject._private.utils import get_transient_and_singleton_dependencies

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from collections.abc import Coroutine
    from collections.abc import Iterator
    from collections.abc import Mapping

    from ninject.types import AsyncIteratorCallable
    from ninject.types import IteratorCallable

P = ParamSpec("P")
R = TypeVar("R")


@decorator
def function(
    func: Callable[P, R],
    *,
    dependencies: Mapping[str, type] | None = None,
) -> Callable[P, R]:
    """Inject dependencies into the given function."""
    transients, singletons = get_transient_and_singleton_dependencies(get_dependencies(func, dependencies))

    @wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        with ExitStack() as stack:
            missing = setdefault_arguments_with_initialized_dependencies(stack, kwargs, transients, singletons)
            sync_update_arguments_by_initializing_dependencies(stack, kwargs, missing)
            return func(*args, **kwargs)

    return wrapper


@decorator
def coroutine(
    func: Callable[P, Coroutine[Any, Any, R]],
    *,
    dependencies: Mapping[str, type] | None = None,
) -> Callable[P, Coroutine[Any, Any, R]]:
    """Inject dependencies into the given coroutine."""
    transients, singletons = get_transient_and_singleton_dependencies(get_dependencies(func, dependencies))

    @wraps(func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        async with AsyncExitStack() as stack:
            missing = setdefault_arguments_with_initialized_dependencies(stack, kwargs, transients, singletons)
            await async_update_arguments_by_initializing_dependencies(stack, kwargs, missing)
            return await func(*args, **kwargs)

    return wrapper


@decorator
def iterator(
    func: IteratorCallable[P, R],
    *,
    dependencies: Mapping[str, type] | None = None,
) -> IteratorCallable[P, R]:
    """Inject dependencies into the given iterator."""
    transients, singletons = get_transient_and_singleton_dependencies(get_dependencies(func, dependencies))

    @wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> Iterator[R]:
        with ExitStack() as stack:
            missing = setdefault_arguments_with_initialized_dependencies(stack, kwargs, transients, singletons)
            sync_update_arguments_by_initializing_dependencies(stack, kwargs, missing)
            yield from func(*args, **kwargs)

    return wrapper


@decorator
def asynciterator(
    func: AsyncIteratorCallable[P, R],
    *,
    dependencies: Mapping[str, type] | None = None,
) -> AsyncIteratorCallable[P, R]:
    """Inject dependencies into the given async iterator."""
    transients, singletons = get_transient_and_singleton_dependencies(get_dependencies(func, dependencies))

    @wraps(func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> AsyncIterator[R]:
        async with AsyncExitStack() as stack:
            missing = setdefault_arguments_with_initialized_dependencies(stack, kwargs, transients, singletons)
            await async_update_arguments_by_initializing_dependencies(stack, kwargs, missing)
            async for value in func(*args, **kwargs):
                yield value

    return wrapper
