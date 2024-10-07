from __future__ import annotations

from typing import TYPE_CHECKING
from typing import Any
from typing import ParamSpec
from typing import TypeVar

from ninject._private._provider import SYNC_OR_ASYNC_PROVIDER_INFOS
from ninject._private._provider import SYNC_PROVIDER_INFOS
from ninject._private._provider import ProviderInfo
from ninject._private._provider import SyncProviderInfo
from ninject._private._provider import raise_missing_provider
from ninject._private._singleton import SINGLETONS
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
    dependency_values = SINGLETONS.get()
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
    *,
    sync_context: bool = True,
) -> None:
    sync_provider_infos = SYNC_PROVIDER_INFOS.get()
    for name, types in dependencies.items():
        for cls in types:
            if (provider_info := sync_provider_infos.get(cls)) is not None:
                break
        else:
            raise_missing_provider(types, sync_context=sync_context)
        if (value := SINGLETONS.get().get(cls, undefined)) is undefined:
            arguments[name] = sync_enter_provider_context(stack, provider_info)
        else:
            arguments[name] = value


async def async_update_arguments_by_initializing_dependencies(
    stack: AsyncExitStack,
    arguments: dict[str, Any],
    dependencies: NormDependencies,
) -> None:
    async_provider_infos = SYNC_OR_ASYNC_PROVIDER_INFOS.get()
    for name, types in dependencies.items():
        for cls in types:
            if (provider_info := async_provider_infos.get(cls)) is not None:
                break
        else:
            raise_missing_provider(types, sync_context=False)
        if (value := SINGLETONS.get().get(cls, undefined)) is undefined:
            if provider_info["sync"]:
                arguments[name] = sync_enter_provider_context(stack, provider_info)
            else:
                arguments[name] = await async_enter_provider_context(stack, provider_info)
        else:
            arguments[name] = value


def sync_enter_provider_context(stack: ExitStack | AsyncExitStack, provider_info: SyncProviderInfo) -> Any:
    return provider_info["getter"](stack.enter_context(provider_info["manager"]()))


async def async_enter_provider_context(stack: AsyncExitStack, provider_info: ProviderInfo) -> Any:
    return provider_info["getter"](await stack.enter_async_context(provider_info["manager"]()))
