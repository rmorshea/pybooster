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
from typing import TypeAlias
from typing import TypeVar
from typing import cast

from paramorator import paramorator

from pybooster import injector
from pybooster.core._private._provider import get_provides_type
from pybooster.core._private._provider import set_provider
from pybooster.core._private._utils import NormDependencies
from pybooster.core._private._utils import check_is_concrete_type
from pybooster.core._private._utils import check_is_not_builtin_type
from pybooster.core._private._utils import get_callable_dependencies
from pybooster.core._private._utils import get_callable_return_type
from pybooster.core._private._utils import get_coroutine_return_type
from pybooster.core._private._utils import get_iterator_yield_type

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from collections.abc import Awaitable
    from collections.abc import Iterator
    from collections.abc import Sequence

    from pybooster.core.types import AsyncContextManagerCallable
    from pybooster.core.types import AsyncIteratorCallable
    from pybooster.core.types import ContextManagerCallable
    from pybooster.core.types import Dependencies
    from pybooster.core.types import IteratorCallable

P = ParamSpec("P")
R = TypeVar("R")
G = TypeVar("G")


@paramorator
def function(
    func: Callable[P, R],
    *,
    dependencies: Dependencies | None = None,
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
    dependencies: Dependencies | None = None,
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
    dependencies: Dependencies | None = None,
    provides: type[R] | Callable[..., type[R]] | None = None,
) -> SyncProvider[P, R]:
    """Create a provider from the given iterator function.

    Args:
        func: The function to create a provider from.
        dependencies: The dependencies of the function (infered if not provided).
        provides: The type that the function provides (infered if not provided).
    """
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
    dependencies: Dependencies | None = None,
    provides: type[R] | Callable[..., type[R]] | None = None,
) -> AsyncProvider[P, R]:
    """Create a provider from the given async iterator function.

    Args:
        func: The function to create a provider from.
        dependencies: The dependencies of the function (infered if not provided).
        provides: The type that the function provides (infered if not provided).
    """
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


class _BaseProvider(Generic[P, R]):
    """A base class for providers."""

    def __init__(
        self,
        manager: Callable[P, Any],
        provides: type[R] | Callable[..., type[R]],
        dependencies: NormDependencies,
        *,
        sync: bool,
    ) -> None:
        self._manager = manager
        self._dependencies = dependencies
        self._sync = sync
        self._provides = provides

    def scope(self, *args: P.args, **kwargs: P.kwargs) -> _ProviderScope:
        """Declare this as the provider for the dependency within the context."""
        provides_type = get_provides_type(self._provides, *args, **kwargs)

        try:
            check_is_concrete_type(provides_type)
            check_is_not_builtin_type(provides_type)
        except TypeError as exc:
            msg = f"Invalid provider {self}: {exc}"
            raise TypeError(msg) from None

        dependencies = self._dependencies
        dependency_set = {dependencies[k] for k in dependencies.keys() - set(kwargs)}
        return _ProviderScope(provides_type, lambda: self._manager(*args, **kwargs), dependency_set, sync=self._sync)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self._manager.__module__}.{self._manager.__qualname__})"


class SyncProvider(_BaseProvider[P, R]):
    """A provider that produces a dependency."""

    def __init__(
        self,
        manager: ContextManagerCallable[P, R],
        provides: type[R] | Callable[..., type[R]],
        dependencies: NormDependencies,
    ) -> None:
        super().__init__(manager, provides, dependencies, sync=True)
        self.value = manager

    def __getitem__(self, provides: type[R]) -> SyncProvider[P, R]:
        """Declare a specific type for a generic provider."""
        return SyncProvider(self.value, provides, self._dependencies)


class AsyncProvider(_BaseProvider[P, R]):
    """A provider that produces an async dependency."""

    def __init__(
        self,
        manager: AsyncContextManagerCallable[P, R],
        provides: type[R],
        dependencies: NormDependencies,
    ) -> None:
        super().__init__(manager, provides, dependencies, sync=False)
        self.value = manager

    def __getitem__(self, provides: type[R]) -> AsyncProvider[P, R]:
        """Declare a specific type for a generic provider."""
        return AsyncProvider(self.value, provides, self._dependencies)


class _ProviderScope(AbstractContextManager[None], AbstractAsyncContextManager[None]):
    """A context manager to provide the current value of a dependency."""

    def __init__(
        self,
        provides: type[R],
        manager: ContextManagerCallable[[], R] | AsyncContextManagerCallable[[], R],
        dependency_set: set[Sequence[type]],
        *,
        sync: bool,
    ) -> None:
        self._provides = provides
        self._manager = manager
        self._dependency_set = dependency_set
        self._sync = sync

    def __enter__(self) -> None:
        if hasattr(self, "_reset"):
            msg = "Cannot reuse a context manager."
            raise RuntimeError(msg)
        self._reset = set_provider(self._provides, self._manager, self._dependency_set, sync=self._sync)

    def __exit__(self, *args) -> None:
        try:
            self._reset()
        finally:
            del self._reset

    async def __aenter__(self) -> None:
        return self.__enter__()

    async def __aexit__(self, *args) -> None:
        return self.__exit__(*args)


Provider: TypeAlias = "SyncProvider[P, R] | AsyncProvider[P, R]"
"""A provider that produces a dependency."""
