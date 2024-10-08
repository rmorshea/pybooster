from collections.abc import AsyncIterator
from collections.abc import Iterator
from collections.abc import Mapping
from collections.abc import Sequence
from contextlib import AbstractAsyncContextManager
from contextlib import AbstractContextManager
from typing import Callable
from typing import ParamSpec
from typing import TypeVar

from pybooster._private._utils import make_sentinel_value

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

Dependencies = Mapping[str, type | Sequence[type]]
"""A mapping of parameter names to their possible type or types."""

required = make_sentinel_value(__name__, "required")
"""A sentinel object used to indicate that a dependency is required."""


class ProviderMissingError(RuntimeError):
    """An error raised when a provider is missing."""
