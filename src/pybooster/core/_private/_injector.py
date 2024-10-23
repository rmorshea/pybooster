from __future__ import annotations

from collections.abc import Mapping
from contextlib import AsyncExitStack
from contextlib import ExitStack
from contextvars import ContextVar
from sys import exc_info
from typing import TYPE_CHECKING
from typing import Any
from typing import Callable
from typing import ParamSpec
from typing import TypeVar

from anyio import create_task_group

from pybooster.core._private._solution import get_full_solution
from pybooster.core._private._solution import get_sync_solution
from pybooster.core._private._utils import start_future
from pybooster.core.types import ProviderMissingError

if TYPE_CHECKING:
    from collections.abc import Awaitable
    from collections.abc import Sequence

    from pybooster.core._private._provider import AsyncProviderInfo
    from pybooster.core._private._provider import SyncProviderInfo
    from pybooster.core._private._utils import NormDependencies


P = ParamSpec("P")
R = TypeVar("R")


def sync_set_current_values(types: Sequence[type[R]]) -> tuple[R, Callable[[], None]]:
    arguments: dict[str, R] = {}
    dependencies: dict[str, Sequence[type[R]]] = {"result": types}
    if missing := setdefault_arguments_with_initialized_dependencies(arguments, dependencies):
        stack = ExitStack()
        sync_update_arguments_by_initializing_dependencies(stack, arguments, missing)

        def reset():
            stack.__exit__(*exc_info())

    else:

        def reset():
            pass

    value = arguments["result"]
    _set_current_values(types, value)
    return value, reset


async def async_set_current_values(types: Sequence[type[R]]) -> tuple[R, Callable[[], Awaitable[None]]]:
    arguments: dict[str, R] = {}
    dependencies: dict[str, Sequence[type[R]]] = {"result": types}
    if missing := setdefault_arguments_with_initialized_dependencies(arguments, dependencies):
        stack = AsyncExitStack()
        await async_update_arguments_by_initializing_dependencies(stack, arguments, missing)

        async def reset():
            await stack.__aexit__(*exc_info())

    else:

        async def reset():
            pass

    value = arguments["result"]
    _set_current_values(types, value)
    return value, reset


def _set_current_values(types: Sequence[type[R]], value: R) -> Callable[[], None]:
    token = CURRENT_VALUES.set({**CURRENT_VALUES.get(), **dict.fromkeys(types, value)})
    return lambda: CURRENT_VALUES.reset(token)


def setdefault_arguments_with_initialized_dependencies(
    arguments: dict[str, Any],
    dependencies: NormDependencies,
) -> NormDependencies:
    missing: dict[str, Sequence[type]] = {}
    current_values = CURRENT_VALUES.get()
    for name, types in dependencies.items():
        if name not in arguments:
            for cls in types:
                if cls in current_values:
                    arguments[name] = current_values[cls]
                    break
            else:
                missing[name] = types
    return missing


def sync_update_arguments_by_initializing_dependencies(
    stack: ExitStack | AsyncExitStack,
    arguments: dict[str, Any],
    dependencies: NormDependencies,
) -> None:
    current_values = dict(CURRENT_VALUES.get())
    for providers in get_sync_solution(dependencies):
        _sync_add_current_values(stack, current_values, providers)
    _set_current_values_and_arguments(stack, current_values, arguments, dependencies)


async def async_update_arguments_by_initializing_dependencies(
    stack: AsyncExitStack,
    arguments: dict[str, Any],
    dependencies: NormDependencies,
) -> None:
    current_values = CURRENT_VALUES.get()
    for provider_infos in get_full_solution(dependencies):
        sync_providers: list[SyncProviderInfo] = []
        async_providers: list[AsyncProviderInfo] = []
        for info in provider_infos:
            (sync_providers if info["is_sync"] else async_providers).append(info)
        _sync_add_current_values(stack, current_values, sync_providers)
        await _async_add_current_values(stack, current_values, async_providers)
    _set_current_values_and_arguments(stack, current_values, arguments, dependencies)


def _set_current_values_and_arguments(
    stack: ExitStack | AsyncExitStack,
    current_values: dict[type, Any],
    arguments: dict[str, Any],
    dependencies: NormDependencies,
) -> None:
    token = CURRENT_VALUES.set(current_values)
    if missing := setdefault_arguments_with_initialized_dependencies(arguments, dependencies):
        msg = f"Missing providers for {missing}"
        raise ProviderMissingError(msg)
    stack.callback(CURRENT_VALUES.reset, token)


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


CURRENT_VALUES = ContextVar[Mapping[type, Any]]("CURRENT_VALUES", default={})
