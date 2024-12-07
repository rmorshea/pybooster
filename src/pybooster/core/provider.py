from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from contextlib import AbstractContextManager
from contextlib import asynccontextmanager as _asynccontextmanager
from contextlib import contextmanager as _contextmanager
from functools import wraps
from typing import TYPE_CHECKING
from typing import Any
from typing import Generic
from typing import ParamSpec
from typing import Self
from typing import TypeAlias
from typing import TypeVar
from typing import cast

from paramorator import paramorator

from pybooster._private._provider import get_provides_type
from pybooster._private._utils import get_callable_return_type
from pybooster._private._utils import get_coroutine_return_type
from pybooster._private._utils import get_iterator_yield_type
from pybooster._private._utils import get_required_parameters

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from collections.abc import Awaitable
    from collections.abc import Callable
    from collections.abc import Iterator

    from pybooster.types import AsyncContextManagerCallable
    from pybooster.types import AsyncIteratorCallable
    from pybooster.types import ContextManagerCallable
    from pybooster.types import Hint
    from pybooster.types import HintMap
    from pybooster.types import HintSeq
    from pybooster.types import InferHint
    from pybooster.types import IteratorCallable

P = ParamSpec("P")
R = TypeVar("R")
G = TypeVar("G")


@paramorator
def function(
    func: Callable[P, R],
    *,
    requires: HintMap | HintSeq | None = None,
    provides: Hint | InferHint | None = None,
) -> SyncProvider[P, R]:
    """Create a provider from the given function.

    Args:
        func: The function to create a provider from.
        requires: The dependencies of the function (infered if not provided).
        provides: The type that the function provides (infered if not provided).
    """
    provides = provides or get_callable_return_type(func)

    @wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> Iterator[R]:
        yield func(*args, **kwargs)

    return iterator(wrapper, provides=provides, requires=requires)


@paramorator
def asyncfunction(
    func: Callable[P, Awaitable[R]],
    *,
    requires: HintMap | HintSeq | None = None,
    provides: Hint | InferHint | None = None,
) -> AsyncProvider[P, R]:
    """Create a provider from the given coroutine.

    Args:
        func: The function to create a provider from.
        requires: The dependencies of the function (infered if not provided).
        provides: The type that the function provides (infered if not provided).
    """
    provides = provides or get_coroutine_return_type(func)

    @wraps(func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> AsyncIterator[R]:
        yield await func(*args, **kwargs)

    return asynciterator(wrapper, provides=provides, requires=requires)


@paramorator
def iterator(
    func: IteratorCallable[P, R],
    *,
    requires: HintMap | HintSeq | None = None,
    provides: Hint | InferHint | None = None,
) -> SyncProvider[P, R]:
    """Create a provider from the given iterator function.

    Args:
        func: The function to create a provider from.
        requires: The dependencies of the function (infered if not provided).
        provides: The type that the function provides (infered if not provided).
    """
    provides = provides or get_iterator_yield_type(func, sync=True)
    requires = get_required_parameters(func, requires)
    return SyncProvider(_contextmanager(func), cast("type[R]", provides), requires)


@paramorator
def asynciterator(
    func: AsyncIteratorCallable[P, R],
    *,
    requires: HintMap | HintSeq | None = None,
    provides: Hint | InferHint | None = None,
) -> AsyncProvider[P, R]:
    """Create a provider from the given async iterator function.

    Args:
        func: The function to create a provider from.
        requires: The dependencies of the function (infered if not provided).
        provides: The type that the function provides (infered if not provided).
    """
    provides = provides or get_iterator_yield_type(func, sync=False)
    requires = get_required_parameters(func, requires)
    return AsyncProvider(_asynccontextmanager(func), cast("type[R]", provides), requires)


class _BaseProvider(Generic[R]):
    producer: Any
    provides: Hint | InferHint
    dependencies: HintMap

    def __getitem__(self, provides: Hint) -> Self:
        """Declare a specific type for a generic provider."""
        return type(self)(self.producer, provides, self.dependencies)  # type: ignore[reportCallIssue]

    if TYPE_CHECKING:
        pass
    else:

        def bind(self, *args, **kwargs):
            if disallowed := (self.dependencies.keys() & kwargs):
                msg = f"Cannot bind dependency parameters: {disallowed}"
                raise TypeError(msg)
            producer = self.producer
            provides = get_provides_type(self.provides, *args, **kwargs)
            wrapped = wraps(producer)(lambda **kw: producer(*args, **kwargs, **kw))
            return type(self)(wrapped, provides, self.dependencies)

        def __call__(self, *args, **kwargs):
            return self.producer(*args, **kwargs)


class SyncProvider(Generic[P, R], _BaseProvider[R]):
    """A provider for a dependency."""

    def __init__(
        self,
        producer: ContextManagerCallable[P, R],
        provides: Hint | InferHint,
        dependencies: HintMap,
    ) -> None:
        self.producer = producer
        self.provides = provides
        self.dependencies = dependencies

    if TYPE_CHECKING:

        def bind(self, *args: P.args, **kwargs: P.kwargs) -> SyncProvider[[], R]:
            """Inject the dependencies and produce the dependency."""
            ...

        def __call__(self, *args: P.args, **kwargs: P.kwargs) -> AbstractContextManager[R]: ...  # noqa: D102


class AsyncProvider(Generic[P, R], _BaseProvider[R]):
    """A provider for a dependency."""

    def __init__(
        self,
        producer: AsyncContextManagerCallable[P, R],
        provides: Hint | InferHint,
        dependencies: HintMap,
    ) -> None:
        self.producer = producer
        self.provides = provides
        self.dependencies = dependencies

    if TYPE_CHECKING:

        def bind(self, *args: P.args, **kwargs: P.kwargs) -> AsyncProvider[[], R]:
            """Inject the dependencies and produce the dependency."""
            ...

        def __call__(self, *args: P.args, **kwargs: P.kwargs) -> AbstractAsyncContextManager[R]: ...  # noqa: D102


Provider: TypeAlias = "SyncProvider[P, R] | AsyncProvider[P, R]"
"""A provider for a dependency."""
