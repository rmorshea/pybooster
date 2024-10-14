from __future__ import annotations

from typing import TYPE_CHECKING
from typing import Any
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
    dependency_values = SHARED_VALUES.get()
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
    shared_values = SHARED_VALUES.get()
    for name, cls, info in iter_provider_infos(dependencies, sync=True):
        if cls in shared_values:
            arguments[name] = shared_values[cls]
        else:
            arguments[name] = sync_enter_provider_context(stack, info)


async def async_update_arguments_by_initializing_dependencies(
    stack: AsyncExitStack,
    arguments: dict[str, Any],
    dependencies: NormDependencies,
) -> None:
    shared_values = SHARED_VALUES.get()
    for name, cls, info in iter_provider_infos(dependencies, sync=False):
        if cls in shared_values:
            arguments[name] = shared_values[cls]
        else:
            if info["sync"] is True:
                arguments[name] = sync_enter_provider_context(stack, info)
            else:
                arguments[name] = await async_enter_provider_context(stack, info)


def sync_enter_provider_context(stack: ExitStack | AsyncExitStack, provider_info: SyncProviderInfo) -> Any:
    return provider_info["getter"](stack.enter_context(provider_info["manager"]()))


async def async_enter_provider_context(stack: AsyncExitStack, provider_info: AsyncProviderInfo) -> Any:
    return provider_info["getter"](await stack.enter_async_context(provider_info["manager"]()))
