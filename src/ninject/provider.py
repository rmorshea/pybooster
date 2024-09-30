from __future__ import annotations

from contextlib import asynccontextmanager as _asynccontextmanager
from contextlib import contextmanager as _contextmanager
from functools import wraps
from typing import TYPE_CHECKING
from typing import Callable
from typing import Generic
from typing import Literal
from typing import ParamSpec
from typing import TypeVar

from ninject import injector
from ninject._private.context import set_provider
from ninject._private.utils import decorator
from ninject._private.utils import get_callable_return_type
from ninject._private.utils import get_context_manager_yield_type
from ninject._private.utils import get_coroutine_return_type
from ninject._private.utils import get_dependencies
from ninject._private.utils import get_iterator_yield_type

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from collections.abc import Iterator
    from collections.abc import Mapping

    from ninject.types import AsyncContextManagerCallable
    from ninject.types import AsyncIteratorCallable
    from ninject.types import ContextManagerCallable
    from ninject.types import IteratorCallable

P = ParamSpec("P")
R = TypeVar("R")


@decorator
def function(
    func: Callable[P, R],
    *,
    dependencies: Mapping[str, type] | None = None,
    yields: type[R] | None = None,
) -> SyncProvider[P, R]:
    """Create a provider from the given function."""
    yields = yields or get_callable_return_type(func)

    @wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> Iterator[R]:
        yield func(*args, **kwargs)

    return iterator(wrapper, yields=yields, dependencies=dependencies)


@decorator
def coroutine(
    func: Callable[P, R],
    *,
    dependencies: Mapping[str, type] | None = None,
    yields: type[R] | None = None,
) -> AsyncProvider[P, R]:
    """Create a provider from the given coroutine."""
    yields = yields or get_coroutine_return_type(func)

    @wraps(func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> AsyncIterator[R]:
        yield await func(*args, **kwargs)

    return asynciterator(wrapper, yields=yields, dependencies=dependencies)


@decorator
def iterator(
    func: IteratorCallable[P, R],
    *,
    dependencies: Mapping[str, type] | None = None,
    yields: type[R] | None = None,
) -> SyncProvider[P, R]:
    """Create a provider from the given iterator function."""
    yields = yields or get_iterator_yield_type(func, sync=True)
    if dependencies := get_dependencies(func, dependencies):
        func = injector.iterator(func, dependencies=dependencies)
    return contextmanager(_contextmanager(func), yields=yields)


@decorator
def asynciterator(
    func: AsyncIteratorCallable[P, R],
    *,
    dependencies: Mapping[str, type] | None = None,
    yields: type[R] | None = None,
) -> AsyncProvider[P, R]:
    """Create a provider from the given async iterator function."""
    yields = yields or get_iterator_yield_type(func, sync=False)
    if dependencies := get_dependencies(func, dependencies):
        func = injector.asynciterator(func, dependencies=dependencies)
    return asynccontextmanager(_asynccontextmanager(func), yields=yields)


@decorator
def contextmanager(
    func: ContextManagerCallable[[], R],
    *,
    yields: type[R] | None = None,
) -> SyncProvider[P, R]:
    """Create a provider from the given context manager."""
    yields = yields or get_context_manager_yield_type(func, sync=True)
    return SyncProvider(func, yields=yields)


@decorator
def asynccontextmanager(
    func: AsyncContextManagerCallable[[], R],
    *,
    yields: type[R] | None = None,
) -> AsyncProvider[P, R]:
    """Create a provider from the given async context manager."""
    yields = yields or get_context_manager_yield_type(func, sync=False)
    return AsyncProvider(func, yields=yields)


class _Provider(Generic[P, R]):
    """A provider that can be used to activate a dependency."""

    manager: ContextManagerCallable[P, R] | AsyncContextManagerCallable[P, R]
    yields: type[R]
    sync: bool

    @_contextmanager
    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> Iterator[None]:
        """Activate this provider."""
        reset = set_provider(
            self.yields,
            wraps(self.manager)(lambda: self.manager(*args, **kwargs)),
            sync=self.sync,
        )
        try:
            yield None
        finally:
            reset()


class SyncProvider(_Provider[P, R]):
    """A synchronous provider that can be used to activate a dependency."""

    def __init__(self, manager: ContextManagerCallable[P, R], yields: type[R]) -> None:
        self.manager = manager
        self.yields = yields
        self.sync: Literal[True] = True


class AsyncProvider(_Provider[P, R]):
    """An asynchronous provider that can be used to activate a dependency."""

    def __init__(self, manager: AsyncContextManagerCallable[P, R], yields: type[R]) -> None:
        self.manager = manager
        self.yields = yields
        self.sync: Literal[False] = False
