from __future__ import annotations

from contextvars import ContextVar
from typing import TYPE_CHECKING
from typing import Any
from typing import ParamSpec
from typing import TypeVar

from ninject._private.provider import ASYNC_PROVIDER_INFOS
from ninject._private.provider import SYNC_PROVIDER_INFOS
from ninject._private.provider import ProviderInfo
from ninject._private.provider import SyncProviderInfo
from ninject._private.utils import undefined
from ninject.types import ProviderMissingError

if TYPE_CHECKING:
    from collections.abc import Mapping
    from contextlib import AsyncExitStack
    from contextlib import ExitStack


P = ParamSpec("P")
R = TypeVar("R")


def update_dependency_values(stack: ExitStack | AsyncExitStack, updates: Mapping[type, Any]) -> None:
    token = _DEPENDENCY_VALUES.set({**_DEPENDENCY_VALUES.get(), **updates})
    stack.callback(_DEPENDENCY_VALUES.reset, token)


def setdefault_arguments_with_initialized_dependencies(
    arguments: dict[str, Any],
    dependencies: Mapping[str, type],
) -> dict[str, type]:
    missing: dict[str, type] = {}
    dependency_values = _DEPENDENCY_VALUES.get()
    for name, cls in dependencies.items():
        if name not in arguments:
            if (value := dependency_values.get(cls, undefined)) is not undefined:
                arguments[name] = value
            else:
                missing[name] = cls
    return missing


def sync_update_arguments_by_initializing_dependencies(
    stack: ExitStack | AsyncExitStack,
    arguments: dict[str, Any],
    dependencies: Mapping[str, type],
) -> None:
    new_dependency_values: dict[type, Any] = {}
    sync_provider_infos = SYNC_PROVIDER_INFOS.get()
    for name, cls in dependencies.items():
        try:
            provider_info = sync_provider_infos[cls]
        except KeyError:
            # check if there's an async provider
            if async_provider_infos := ASYNC_PROVIDER_INFOS.get().get(cls):
                msg = f"Async provider {async_provider_infos['manager']} cannot be used in a sync context."
                raise ProviderMissingError(msg) from None
            msg = f"No provider for {cls} is active"
            raise ProviderMissingError(msg) from None
        value = arguments[name] = sync_enter_provider_context(stack, provider_info)
        if provider_info["singleton"]:
            new_dependency_values[cls] = value

    token = _DEPENDENCY_VALUES.set(new_dependency_values)
    stack.callback(_DEPENDENCY_VALUES.reset, token)


async def async_update_arguments_by_initializing_dependencies(
    stack: AsyncExitStack,
    arguments: dict[str, Any],
    dependencies: Mapping[str, type],
) -> None:
    missing: dict[str, type] = {}
    new_dependency_values: dict[type, Any] = {}
    async_provider_infos = ASYNC_PROVIDER_INFOS.get()
    for name, cls in dependencies.items():
        if (provider_info := async_provider_infos.get(cls)) is None:
            missing[name] = cls
            continue
        arguments[name] = await async_enter_provider_context(stack, provider_info)
        if provider_info["singleton"]:
            new_dependency_values[cls] = arguments[name]
    token = _DEPENDENCY_VALUES.set(new_dependency_values)
    stack.callback(_DEPENDENCY_VALUES.reset, token)
    sync_update_arguments_by_initializing_dependencies(stack, arguments, missing)


def sync_enter_provider_context(stack: ExitStack | AsyncExitStack, provider_info: SyncProviderInfo) -> Any:
    return provider_info["getter"](stack.enter_context(provider_info["manager"]()))


async def async_enter_provider_context(stack: AsyncExitStack, provider_info: ProviderInfo) -> Any:
    return provider_info["getter"](await stack.enter_async_context(provider_info["manager"]()))


_DEPENDENCY_VALUES: ContextVar[Mapping[type, Any]] = ContextVar("DEPENDENCIES", default={})
