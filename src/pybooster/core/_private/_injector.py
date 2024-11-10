from __future__ import annotations

from collections.abc import Mapping
from contextvars import ContextVar
from typing import TYPE_CHECKING
from typing import Any
from typing import ParamSpec
from typing import TypeVar

from anyio import create_task_group

from pybooster.core._private._solution import get_full_solution
from pybooster.core._private._solution import get_sync_solution
from pybooster.core._private._utils import start_future
from pybooster.types import ProviderMissingError

if TYPE_CHECKING:
    from collections.abc import Sequence
    from contextlib import AsyncExitStack
    from contextlib import ExitStack

    from pybooster.core._private._provider import AsyncProviderInfo
    from pybooster.core._private._provider import SyncProviderInfo
    from pybooster.core._private._utils import NormParamTypes


P = ParamSpec("P")
R = TypeVar("R")


def update_argument_from_current_values(arguments: dict[str, Any], required_params: NormParamTypes) -> NormParamTypes:
    return _try_update_arguments_from_current_values_or_fallbacks(
        arguments, required_params, dict(CURRENT_VALUES.get())
    )


def sync_update_arguments_from_providers_or_fallbacks(
    stack: ExitStack | AsyncExitStack,
    arguments: dict[str, Any],
    required_params: NormParamTypes,
    fallbacks: Mapping[str, Any],
) -> None:
    current_values = dict(CURRENT_VALUES.get())
    token = CURRENT_VALUES.set(current_values)
    stack.callback(CURRENT_VALUES.reset, token)
    for providers in get_sync_solution(required_params):
        _sync_add_current_values(stack, current_values, providers)
    _update_arguments_from_current_values_or_fallbacks(arguments, required_params, current_values, fallbacks)


async def async_update_arguments_from_providers_or_fallbacks(
    stack: AsyncExitStack,
    arguments: dict[str, Any],
    required_params: NormParamTypes,
    fallbacks: Mapping[str, Any],
) -> None:
    current_values = dict(CURRENT_VALUES.get())
    token = CURRENT_VALUES.set(current_values)
    stack.callback(CURRENT_VALUES.reset, token)
    for provider_infos in get_full_solution(required_params):
        sync_providers: list[SyncProviderInfo] = []
        async_providers: list[AsyncProviderInfo] = []
        for info in provider_infos:
            (sync_providers if info["is_sync"] else async_providers).append(info)
        _sync_add_current_values(stack, current_values, sync_providers)
        await _async_add_current_values(stack, current_values, async_providers)
    _update_arguments_from_current_values_or_fallbacks(arguments, required_params, current_values, fallbacks)


def _sync_add_current_values(
    stack: ExitStack | AsyncExitStack,
    current_values: dict[type, Any],
    providers: Sequence[AsyncProviderInfo],
) -> None:
    for p in providers:
        if (cls := p["provides"]) not in current_values:
            current_values[cls] = _sync_enter_provider_context(stack, p)


async def _async_add_current_values(
    stack: AsyncExitStack,
    current_values: dict[type, Any],
    providers: Sequence[AsyncProviderInfo],
) -> None:
    if providers_len := len(providers):
        if providers_len == 1:
            p = providers[0]
            if (cls := p["provides"]) not in current_values:
                current_values[cls] = await _async_enter_provider_context(stack, p)
        else:
            missing = [p for p in providers if p["provides"] not in current_values]
            async with create_task_group() as tg:
                provider_futures = [(p, start_future(tg, _async_enter_provider_context(stack, p))) for p in missing]
            for p, f in provider_futures:
                current_values[p["provides"]] = f()


def _sync_enter_provider_context(stack: ExitStack | AsyncExitStack, provider_info: SyncProviderInfo) -> Any:
    return provider_info["getter"](stack.enter_context(provider_info["producer"]()))


async def _async_enter_provider_context(stack: AsyncExitStack, provider_info: AsyncProviderInfo) -> Any:
    return provider_info["getter"](await stack.enter_async_context(provider_info["producer"]()))


def _update_arguments_from_current_values_or_fallbacks(
    arguments: dict[str, Any],
    required_params: NormParamTypes,
    current_values: Mapping[type, Any],
    fallbacks: dict[str, Any],
) -> None:
    if missing := _try_update_arguments_from_current_values_or_fallbacks(
        arguments,
        required_params,
        current_values,
        fallbacks,
    ):
        msg = f"Missing providers for {missing}"
        raise ProviderMissingError(msg)


def _try_update_arguments_from_current_values_or_fallbacks(
    arguments: dict[str, Any],
    required_params: NormParamTypes,
    current_values: Mapping[type, Any],
    fallbacks: Mapping[str, Any] = {},
) -> NormParamTypes:
    missing: dict[str, Sequence[type]] = {}
    for name, types in required_params.items():
        if name not in arguments:
            for cls in types:
                if cls in current_values:
                    arguments[name] = current_values[cls]
                    break
            else:
                if name in fallbacks:
                    arguments[name] = fallbacks[name]
                else:
                    missing[name] = types
    return missing


CURRENT_VALUES = ContextVar[Mapping[type, Any]]("CURRENT_VALUES", default={})
