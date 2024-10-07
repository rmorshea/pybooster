from __future__ import annotations

from contextlib import asynccontextmanager
from contextlib import contextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING
from typing import Any
from typing import ParamSpec
from typing import TypeVar

from ninject._private._provider import SYNC_OR_ASYNC_PROVIDER_INFOS
from ninject._private._provider import SYNC_PROVIDER_INFOS
from ninject._private._provider import raise_missing_provider

if TYPE_CHECKING:
    from collections.abc import Mapping
    from collections.abc import Sequence


P = ParamSpec("P")
R = TypeVar("R")


@contextmanager
def sync_singleton(types: Sequence[type[R]]) -> R:
    for cls in types:
        if (provider_info := SYNC_PROVIDER_INFOS.get().get(cls)) is not None:
            break
    else:
        raise_missing_provider(types, sync_context=True)
    with provider_info["manager"]() as value:
        token = SINGLETONS.set({**SINGLETONS.get(), cls: value})
        try:
            yield value
        finally:
            SINGLETONS.reset(token)


@asynccontextmanager
async def async_singleton(types: Sequence[type[R]]) -> R:
    for cls in types:
        if (provider_info := SYNC_OR_ASYNC_PROVIDER_INFOS.get().get(cls)) is not None:
            break
    else:
        raise_missing_provider(types, sync_context=False)
    async with provider_info["manager"]() as value:
        token = SINGLETONS.set({**SINGLETONS.get(), cls: value})
        try:
            yield value
        finally:
            SINGLETONS.reset(token)


SINGLETONS: ContextVar[Mapping[type, Any]] = ContextVar("SINGLETONS", default={})
