from __future__ import annotations

from typing import TYPE_CHECKING
from typing import Any
from typing import ParamSpec
from typing import TypeVar

from ninject._private._provider import ProviderInfo
from ninject._private._provider import SyncProviderInfo
from ninject._private._provider import iter_provider_infos
from ninject._private._shared import SHARED_VALUES
from ninject._private._utils import NormDependencies
from ninject._private._utils import undefined

if TYPE_CHECKING:
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
    dependency_values = SHARED_VALUES.get()
    for name, types in dependencies.items():
        if name not in arguments:
            for cls in types:
                if (value := dependency_values.get(cls, undefined)) is not undefined:
                    arguments[name] = value
                    break
            else:
                missing[name] = types
    return missing


def sync_update_arguments_by_initializing_dependencies(
    stack: ExitStack | AsyncExitStack,
    arguments: dict[str, Any],
    dependencies: NormDependencies,
) -> None:
    for name, cls, info in iter_provider_infos(dependencies, sync=True):
        if (value := SHARED_VALUES.get().get(cls, undefined)) is undefined:
            arguments[name] = sync_enter_provider_context(stack, info)
        else:
            arguments[name] = value


async def async_update_arguments_by_initializing_dependencies(
    stack: AsyncExitStack,
    arguments: dict[str, Any],
    dependencies: NormDependencies,
) -> None:
    for name, cls, info in iter_provider_infos(dependencies, sync=False):
        if (value := SHARED_VALUES.get().get(cls, undefined)) is undefined:
            if info["sync"] is True:
                arguments[name] = sync_enter_provider_context(stack, info)
            else:
                arguments[name] = await async_enter_provider_context(stack, info)
        else:
            arguments[name] = value


def sync_enter_provider_context(stack: ExitStack | AsyncExitStack, provider_info: SyncProviderInfo) -> Any:
    return provider_info["getter"](stack.enter_context(provider_info["manager"]()))


async def async_enter_provider_context(stack: AsyncExitStack, provider_info: ProviderInfo) -> Any:
    return provider_info["getter"](await stack.enter_async_context(provider_info["manager"]()))
