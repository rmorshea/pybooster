from __future__ import annotations

from contextvars import ContextVar
from typing import TYPE_CHECKING
from typing import Any
from typing import Callable
from typing import ParamSpec
from typing import TypeVar

from pybooster.core._private._provider import AsyncProviderInfo
from pybooster.core._private._provider import SyncProviderInfo
from pybooster.core._private._provider import iter_provider_infos
from pybooster.core._private._shared import SHARED_VALUES

if TYPE_CHECKING:
    from collections.abc import Sequence
    from contextlib import AsyncExitStack
    from contextlib import ExitStack

    from pybooster.core._private._utils import NormDependencies


P = ParamSpec("P")
R = TypeVar("R")


def setdefault_arguments_with_initialized_dependencies(
    arguments: dict[str, Any],
    dependencies: NormDependencies,
) -> NormDependencies:
    missing: dict[str, Sequence[type]] = {}
    shared_values = SHARED_VALUES.get()
    injector_values = _INJECTOR_VALUES.get() or {}
    for name, types in dependencies.items():
        if name not in arguments:
            for cls in types:
                if cls in shared_values:
                    arguments[name] = shared_values[cls]
                    break
                if cls in injector_values:
                    arguments[name] = injector_values[cls]
                    break
            else:
                missing[name] = types
    return missing


def sync_update_arguments_by_initializing_dependencies(
    stack: ExitStack | AsyncExitStack,
    arguments: dict[str, Any],
    dependencies: NormDependencies,
) -> None:
    shared_values = SHARED_VALUES.get()
    injector_values, reset_injector_values = _get_injector_values()
    try:
        for name, cls, info in iter_provider_infos(dependencies, sync=True):
            if cls in injector_values:
                arguments[name] = injector_values[cls]
            elif cls in shared_values:
                injector_values[cls] = arguments[name] = shared_values[cls]
            else:
                injector_values[cls] = arguments[name] = sync_enter_provider_context(stack, info)
    finally:
        reset_injector_values()


async def async_update_arguments_by_initializing_dependencies(
    stack: AsyncExitStack,
    arguments: dict[str, Any],
    dependencies: NormDependencies,
) -> None:
    shared_values = SHARED_VALUES.get()
    injector_values, reset_injector_values = _get_injector_values()
    try:
        for name, cls, info in iter_provider_infos(dependencies, sync=False):
            if cls in injector_values:
                arguments[name] = injector_values[cls]
            elif cls in shared_values:
                injector_values[cls] = arguments[name] = shared_values[cls]
            else:
                if info["sync"] is True:
                    injector_values[cls] = arguments[name] = sync_enter_provider_context(stack, info)
                else:
                    injector_values[cls] = arguments[name] = await async_enter_provider_context(stack, info)
    finally:
        reset_injector_values()


def sync_enter_provider_context(stack: ExitStack | AsyncExitStack, provider_info: SyncProviderInfo) -> Any:
    return provider_info["getter"](stack.enter_context(provider_info["manager"]()))


async def async_enter_provider_context(stack: AsyncExitStack, provider_info: AsyncProviderInfo) -> Any:
    return provider_info["getter"](await stack.enter_async_context(provider_info["manager"]()))


def _get_injector_values() -> tuple[dict[type, Any], Callable[[], None]]:
    token = _INJECTOR_VALUES.set(injector_values := {}) if (injector_values := _INJECTOR_VALUES.get()) is None else None
    return injector_values, lambda: token and _INJECTOR_VALUES.reset(token)


_INJECTOR_VALUES: ContextVar[dict[type, Any] | None] = ContextVar("INJECTOR_VALUES")
