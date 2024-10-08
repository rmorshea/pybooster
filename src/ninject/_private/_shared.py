from __future__ import annotations

from contextlib import asynccontextmanager
from contextlib import contextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING
from typing import Any
from typing import Callable
from typing import ParamSpec
from typing import TypeVar

from ninject._private._provider import get_provider_info
from ninject._private._utils import undefined

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from collections.abc import Iterator
    from collections.abc import Mapping
    from collections.abc import Sequence


P = ParamSpec("P")
R = TypeVar("R")


@contextmanager
def sync_shared_context(types: Sequence[type[R]], value: R) -> Iterator[R]:
    if value is not undefined:
        reset = _set_shared_value(types, value)
        try:
            yield value
        finally:
            reset()
    else:
        with get_provider_info(types, sync=True)["manager"]() as value:
            reset = _set_shared_value(types, value)
            try:
                yield value
            finally:
                reset()


@asynccontextmanager
async def async_shared_context(types: Sequence[type[R]], value: R) -> AsyncIterator[R]:
    if value is not undefined:
        reset = _set_shared_value(types, value)
        try:
            yield value
        finally:
            reset()
    else:
        async with get_provider_info(types, sync=False)["manager"]() as value:
            token = SHARED_VALUES.set({**SHARED_VALUES.get(), **dict.fromkeys(types, value)})
            try:
                yield value
            finally:
                SHARED_VALUES.reset(token)


def _set_shared_value(types: Sequence[type[R]], value: R) -> Callable[[], None]:
    token = SHARED_VALUES.set({**SHARED_VALUES.get(), **dict.fromkeys(types, value)})
    return lambda: SHARED_VALUES.reset(token)


SHARED_VALUES: ContextVar[Mapping[type, Any]] = ContextVar("SINGLETONS", default={})
