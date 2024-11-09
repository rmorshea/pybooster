from collections.abc import AsyncIterator
from collections.abc import Iterator
from collections.abc import Mapping
from collections.abc import Sequence
from contextlib import AbstractAsyncContextManager
from contextlib import AbstractContextManager
from typing import Callable
from typing import ParamSpec
from typing import TypeVar
from typing import cast

from pybooster.core._private._utils import FallbackMarker as _FallbackMarker
from pybooster.core._private._utils import make_sentinel_value

P = ParamSpec("P")
R = TypeVar("R")
Y = TypeVar("Y")
S = TypeVar("S")

IteratorCallable = Callable[P, Iterator[R]]
"""A callable that returns an iterator."""
AsyncIteratorCallable = Callable[P, AsyncIterator[R]]
"""A callable that returns an async iterator."""
ContextManagerCallable = Callable[P, AbstractContextManager[R]]
"""A callable that returns a context manager."""
AsyncContextManagerCallable = Callable[P, AbstractAsyncContextManager[R]]
"""A callable that returns an async context manager."""
AnyContextManagerCallable = Callable[P, AbstractContextManager[R] | AbstractAsyncContextManager[R]]
"""A callable that returns any kind of context manager."""

Dependencies = Mapping[str, type | Sequence[type]]
"""A mapping of parameter names to their possible type or types."""

required = make_sentinel_value(__name__, "required")
"""A sentinel object used to indicate that a dependency is required."""


class Fallback:
    """A sentinel object used to indicate that a dependency should fallback to its default."""

    def __getitem__(self, value: R) -> R:
        return cast(R, _FallbackMarker(value))


fallback = Fallback()
"""Indicate that a dependency should fallback to its default by using `fallback[default]`."""
del Fallback


class ProviderMissingError(RuntimeError):
    """An error raised when a provider is missing."""
