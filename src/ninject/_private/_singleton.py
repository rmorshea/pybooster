from __future__ import annotations

from contextlib import asynccontextmanager
from contextlib import contextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING
from typing import Any
from typing import ParamSpec
from typing import TypeVar

from ninject._private._provider import get_provider_info

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from collections.abc import Iterator
    from collections.abc import Mapping
    from collections.abc import Sequence


P = ParamSpec("P")
R = TypeVar("R")


@contextmanager
def sync_singleton(types: Sequence[type[R]]) -> Iterator[R]:
    with get_provider_info(types, sync=True)["manager"]() as value:
        token = SINGLETONS.set({**SINGLETONS.get(), **dict.fromkeys(types, value)})
        try:
            yield value
        finally:
            SINGLETONS.reset(token)


@asynccontextmanager
async def async_singleton(types: Sequence[type[R]]) -> AsyncIterator[R]:
    async with get_provider_info(types, sync=False)["manager"]() as value:
        token = SINGLETONS.set({**SINGLETONS.get(), **dict.fromkeys(types, value)})
        try:
            yield value
        finally:
            SINGLETONS.reset(token)


SINGLETONS: ContextVar[Mapping[type, Any]] = ContextVar("SINGLETONS", default={})
