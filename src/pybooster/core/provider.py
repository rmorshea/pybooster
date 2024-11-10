from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from contextlib import AbstractContextManager
from contextlib import asynccontextmanager as _asynccontextmanager
from contextlib import contextmanager as _contextmanager
from functools import wraps
from typing import TYPE_CHECKING
from typing import Any
from typing import Callable
from typing import Generic
from typing import ParamSpec
from typing import Self
from typing import TypeAlias
from typing import TypeVar
from typing import cast
from typing import overload

from paramorator import paramorator

from pybooster import injector
from pybooster.core._private._provider import get_provides_type
from pybooster.core._private._utils import NormParamTypes
from pybooster.core._private._utils import get_callable_dependencies
from pybooster.core._private._utils import get_callable_fallbacks
from pybooster.core._private._utils import get_callable_return_type
from pybooster.core._private._utils import get_coroutine_return_type
from pybooster.core._private._utils import get_iterator_yield_type

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from collections.abc import Awaitable
    from collections.abc import Iterator

    from pybooster.types import AsyncContextManagerCallable
    from pybooster.types import AsyncIteratorCallable
    from pybooster.types import ContextManagerCallable
    from pybooster.types import IteratorCallable
    from pybooster.types import ParamTypes

P = ParamSpec("P")
R = TypeVar("R")
G = TypeVar("G")


@overload
def singleton(provides: Callable[[G], R], value: G) -> SyncProvider[[], R]: ...


@overload
def singleton(provides: type[R], value: R) -> SyncProvider[[], R]: ...


def singleton(provides: type[R] | Callable[[Any], R], value: R) -> SyncProvider[[], R]:
    """Create a provider for a singleton value.

    Args:
        provides: The type that the value provides.
        value: The value to provide
    """
    return function(lambda: value, provides=provides)


@paramorator
def function(
    func: Callable[P, R],
    *,
    dependencies: ParamTypes | None = None,
    provides: type[R] | Callable[..., type[R]] | None = None,
) -> SyncProvider[P, R]:
    """Create a provider from the given function.

    Args:
        func: The function to create a provider from.
        dependencies: The dependencies of the function (infered if not provided).
        provides: The type that the function provides (infered if not provided).
    """
    provides = provides or get_callable_return_type(func)

    @wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> Iterator[R]:
        yield func(*args, **kwargs)

    return iterator(wrapper, provides=provides, dependencies=dependencies)


@paramorator
def asyncfunction(
    func: Callable[P, Awaitable[R]],
    *,
    dependencies: ParamTypes | None = None,
    provides: type[R] | Callable[..., type[R]] | None = None,
) -> AsyncProvider[P, R]:
    """Create a provider from the given coroutine.

    Args:
        func: The function to create a provider from.
        dependencies: The dependencies of the function (infered if not provided).
        provides: The type that the function provides (infered if not provided).
    """
    provides = provides or get_coroutine_return_type(func)

    @wraps(func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> AsyncIterator[R]:
        yield await func(*args, **kwargs)

    return asynciterator(wrapper, provides=provides, dependencies=dependencies)


@paramorator
def iterator(
    func: IteratorCallable[P, R],
    *,
    dependencies: ParamTypes | None = None,
    provides: type[R] | Callable[..., type[R]] | None = None,
) -> SyncProvider[P, R]:
    """Create a provider from the given iterator function.

    Args:
        func: The function to create a provider from.
        dependencies: The dependencies of the function (infered if not provided).
        provides: The type that the function provides (infered if not provided).
    """
    if fallbacks := get_callable_fallbacks(func):
        msg = f"Providers cannot have fallbacks - found {fallbacks} in {func}"
        raise TypeError(msg)
    provides = provides or get_iterator_yield_type(func, sync=True)
    norm_dependencies = get_callable_dependencies(func, dependencies)
    return SyncProvider(
        injector.contextmanager(func, dependencies=norm_dependencies) if norm_dependencies else _contextmanager(func),
        cast(type[R], provides),
        norm_dependencies,
    )


@paramorator
def asynciterator(
    func: AsyncIteratorCallable[P, R],
    *,
    dependencies: ParamTypes | None = None,
    provides: type[R] | Callable[..., type[R]] | None = None,
) -> AsyncProvider[P, R]:
    """Create a provider from the given async iterator function.

    Args:
        func: The function to create a provider from.
        dependencies: The dependencies of the function (infered if not provided).
        provides: The type that the function provides (infered if not provided).
    """
    if fallbacks := get_callable_fallbacks(func):
        msg = f"Providers cannot have fallbacks - found {fallbacks} in {func}"
        raise TypeError(msg)
    provides = provides or get_iterator_yield_type(func, sync=False)
    norm_dependencies = get_callable_dependencies(func, dependencies)
    return AsyncProvider(
        (
            injector.asynccontextmanager(func, dependencies=norm_dependencies)
            if norm_dependencies
            else _asynccontextmanager(func)
        ),
        cast(type[R], provides),
        norm_dependencies,
    )


class SyncProvider(Generic[P, R]):
    """A provider for a dependency."""

    def __init__(
        self,
        producer: ContextManagerCallable[P, R],
        provides: type[R] | Callable[..., type[R]],
        dependencies: NormParamTypes,
    ) -> None:
        self.producer = producer
        self.provides = provides
        self.dependencies = dependencies

    def bind(self, *args: P.args, **kwargs: P.kwargs) -> Self[[], R]:
        """Inject the dependencies and produce the dependency."""
        return type(self)(
            lambda: self.producer(*args, **kwargs),
            get_provides_type(self.provides, *args, **kwargs),
            self.dependencies,
        )

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> AbstractContextManager[R]:  # noqa: D102
        return self.producer(*args, **kwargs)

    def __getitem__(self, provides: type[R]) -> Self:
        """Declare a specific type for a generic provider."""
        return type(self)(self.producer, provides, self.dependencies)


class AsyncProvider(Generic[P, R]):
    """A provider for a dependency."""

    def __init__(
        self,
        producer: AsyncContextManagerCallable[P, R],
        provides: type[R] | Callable[..., type[R]],
        dependencies: NormParamTypes,
    ) -> None:
        self.producer = producer
        self.provides = provides
        self.dependencies = dependencies

    def bind(self, *args: P.args, **kwargs: P.kwargs) -> Self[[], R]:
        """Inject the dependencies and produce the dependency."""
        return type(self)(
            lambda: self.producer(*args, **kwargs),
            get_provides_type(self.provides, *args, **kwargs),
            self.dependencies,
        )

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> AbstractAsyncContextManager[R]:  # noqa: D102
        return self.producer(*args, **kwargs)

    def __getitem__(self, provides: type[R]) -> Self:
        """Declare a specific type for a generic provider."""
        return type(self)(self.producer, provides, self.dependencies)


Provider: TypeAlias = "SyncProvider[P, R] | AsyncProvider[P, R]"
"""A provider for a dependency."""
