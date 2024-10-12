from __future__ import annotations

from contextlib import asynccontextmanager
from contextlib import contextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING
from typing import Any
from typing import Callable
from typing import ParamSpec
from typing import TypeVar

from pybooster.core._private._provider import AsyncProviderInfo
from pybooster.core._private._provider import SyncProviderInfo
from pybooster.core._private._provider import get_provider_info
from pybooster.core._private._provider import iter_provider_infos
from pybooster.core._private._utils import NormDependencies
from pybooster.core._private._utils import undefined

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from collections.abc import Iterator
    from collections.abc import Mapping
    from collections.abc import Sequence
    from contextlib import AsyncExitStack
    from contextlib import ExitStack


P = ParamSpec("P")
R = TypeVar("R")


def setdefault_arguments_with_initialized_dependencies(
    arguments: dict[str, Any],
    dependencies: NormDependencies,
) -> NormDependencies:
    missing: dict[str, Sequence[type]] = {}
    dependency_values = _SHARED_VALUES.get()
    for name, types in dependencies.items():
        if name not in arguments:
            for cls in types:
                if cls in dependency_values:
                    arguments[name] = dependency_values[cls]
                    break
            else:
                missing[name] = types
    return missing


def sync_update_arguments_by_initializing_dependencies(
    stack: ExitStack | AsyncExitStack,
    arguments: dict[str, Any],
    dependencies: NormDependencies,
) -> None:
    shared_values = _SHARED_VALUES.get()
    for name, cls, info in iter_provider_infos(dependencies, sync=True):
        if cls not in shared_values:
            arguments[name] = sync_enter_provider_context(stack, info)
        else:
            arguments[name] = shared_values[cls]


async def async_update_arguments_by_initializing_dependencies(
    stack: AsyncExitStack,
    arguments: dict[str, Any],
    dependencies: NormDependencies,
) -> None:
    shared_values = _SHARED_VALUES.get()
    for name, cls, info in iter_provider_infos(dependencies, sync=False):
        if cls not in shared_values:
            if info["sync"] is True:
                arguments[name] = sync_enter_provider_context(stack, info)
            else:
                arguments[name] = await async_enter_provider_context(stack, info)
        else:
            arguments[name] = shared_values[cls]


def sync_enter_provider_context(stack: ExitStack | AsyncExitStack, provider_info: SyncProviderInfo) -> Any:
    return provider_info["getter"](stack.enter_context(provider_info["manager"]()))


async def async_enter_provider_context(stack: AsyncExitStack, provider_info: AsyncProviderInfo) -> Any:
    return provider_info["getter"](await stack.enter_async_context(provider_info["manager"]()))


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
            reset = _set_shared_value(types, value)
            try:
                yield value
            finally:
                reset()


def _set_shared_value(types: Sequence[type[R]], value: R) -> Callable[[], None]:
    token = _SHARED_VALUES.set({**_SHARED_VALUES.get(), **dict.fromkeys(types, value)})
    return lambda: _SHARED_VALUES.reset(token)


_SHARED_VALUES: ContextVar[Mapping[type, Any]] = ContextVar("SINGLETONS", default={})
