from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from collections.abc import Mapping
from contextvars import ContextVar
from typing import TYPE_CHECKING
from typing import Any
from typing import ParamSpec
from typing import TypeVar

from anyio import create_task_group

from pybooster._private._solution import FULL_SOLUTION
from pybooster._private._solution import SYNC_SOLUTION
from pybooster._private._solution import Solution
from pybooster._private._utils import start_future
from pybooster._private._utils import undefined
from pybooster.types import HintDict
from pybooster.types import HintMap
from pybooster.types import InjectionError

if TYPE_CHECKING:

    from pybooster._private._provider import AsyncProviderInfo
    from pybooster._private._provider import ProviderInfo
    from pybooster._private._provider import SyncProviderInfo
    from pybooster._private._utils import AsyncFastStack
    from pybooster._private._utils import FastStack


P = ParamSpec("P")
R = TypeVar("R")


def overwrite_values(values: Mapping[type, Any]) -> Callable[[], None]:
    """Overwrite the current values of the given dependencies."""
    new_values = {**_CURRENT_VALUES.get(), **values}
    token = _CURRENT_VALUES.set(new_values)
    return lambda: _CURRENT_VALUES.reset(token)


def sync_inject_keywords(
    stack: FastStack,
    required_params: HintMap,
    overwrite_values: dict[str, Any],
    *,
    keep_current_values: bool = False,
) -> None:
    solution = SYNC_SOLUTION.get()
    current_values = dict(_CURRENT_VALUES.get())

    _inject_overwrite_values(overwrite_values, required_params, current_values, solution)
    missing_params = {k: required_params[k] for k in required_params.keys() - overwrite_values}
    _inject_current_values(overwrite_values, missing_params, current_values)

    if not missing_params:
        return

    current_values_token = _CURRENT_VALUES.set(current_values)
    try:
        _sync_inject_provider_values(stack, overwrite_values, missing_params, current_values, solution)
        _check_for_missing_params(missing_params)
    finally:
        if keep_current_values:
            stack.push_callback(_CURRENT_VALUES.reset, current_values_token)
        else:
            _CURRENT_VALUES.reset(current_values_token)


async def async_inject_keywords(
    stack: AsyncFastStack,
    required_params: HintMap,
    overwrite_values: dict[str, Any],
    *,
    keep_current_values: bool = False,
) -> None:
    solution = FULL_SOLUTION.get()
    current_values = dict(_CURRENT_VALUES.get())

    _inject_overwrite_values(overwrite_values, required_params, current_values, solution)
    missing_params = {k: required_params[k] for k in required_params.keys() - overwrite_values}
    _inject_current_values(overwrite_values, missing_params, current_values)

    if not missing_params:
        return

    current_values_token = _CURRENT_VALUES.set(current_values)
    try:
        await _async_inject_provider_values(stack, overwrite_values, missing_params, current_values, solution)
        _check_for_missing_params(missing_params)
    finally:
        if keep_current_values:
            stack.push_callback(_CURRENT_VALUES.reset, current_values_token)
        else:
            _CURRENT_VALUES.reset(current_values_token)


def _inject_overwrite_values(
    overwrite_values: dict[str, Any],
    required_params: HintMap,
    current_values: dict[type, Any],
    solution: Solution,
) -> None:
    to_invalidate: set[type] = set()
    for name in required_params.keys() & overwrite_values:
        if current_values.get(cls := required_params[name], undefined) is not (new_val := overwrite_values[name]):
            current_values[cls] = new_val
            to_invalidate.update(solution.descendant_types(cls))
    for cls in to_invalidate:
        current_values.pop(cls, None)


def _inject_current_values(
    kwargs: dict[str, Any],
    missing_params: HintDict,
    current_values: Mapping[type, Any],
) -> None:
    for name, cls in tuple(missing_params.items()):
        if cls in current_values:
            kwargs[name] = current_values[cls]
            del missing_params[name]


def _sync_inject_provider_values(
    stack: FastStack,
    kwargs: dict[str, Any],
    missing_params: HintDict,
    current_values: dict[type, Any],
    solution: Solution[SyncProviderInfo],
) -> None:
    param_name_by_type = _get_param_name_by_type_map(solution, missing_params)
    for provider_generation in solution.execution_order_for(param_name_by_type.keys()):
        for provider_info in provider_generation:
            if (cls := provider_info["provides"]) not in current_values:
                value = current_values[cls] = _sync_enter_provider_context(stack, provider_info)
                for name in param_name_by_type[cls]:
                    kwargs[name] = value
                    del missing_params[name]


async def _async_inject_provider_values(
    stack: AsyncFastStack,
    kwargs: dict[str, Any],
    missing_params: HintDict,
    current_values: dict[type, Any],
    solution: Solution[ProviderInfo],
) -> None:
    param_name_by_type = _get_param_name_by_type_map(solution, missing_params)
    for provider_generation in solution.execution_order_for(param_name_by_type.keys()):
        match provider_generation:
            case [provider_info]:
                if provider_info["is_sync"] is True:
                    value = _sync_enter_provider_context(stack, provider_info)
                else:
                    value = await _async_enter_provider_context(stack, provider_info)
                for name in param_name_by_type[cls := provider_info["provides"]]:
                    kwargs[name] = current_values[cls] = value
                    del missing_params[name]
            case [*provider_infos]:
                async_infos: list[AsyncProviderInfo] = []
                for provider_info in provider_infos:
                    if provider_info["is_sync"] is True:
                        value = _sync_enter_provider_context(stack, provider_info)
                        for name in param_name_by_type[cls := provider_info["provides"]]:
                            kwargs[name] = current_values[cls] = value
                            del missing_params[name]
                    else:
                        async_infos.append(provider_info)

                async with create_task_group() as tg:
                    provider_futures = [
                        (p, start_future(tg, _async_enter_provider_context(stack, p))) for p in async_infos
                    ]
                for p, f in provider_futures:
                    value = f()
                    for name in param_name_by_type[cls := p["provides"]]:
                        kwargs[name] = current_values[cls] = value
                        del missing_params[name]


def _get_param_name_by_type_map(solution: Solution, missing_params: HintMap) -> dict[type, list[str]]:
    solution_infos = solution.infos
    param_name_by_type: defaultdict[type, list[str]] = defaultdict(list)
    for name, cls in missing_params.items():
        if cls in solution_infos:
            param_name_by_type[cls].append(name)
    return param_name_by_type


def _sync_enter_provider_context(stack: FastStack | AsyncFastStack, provider_info: SyncProviderInfo) -> Any:
    return provider_info["getter"](stack.enter_context(provider_info["producer"]()))


async def _async_enter_provider_context(stack: AsyncFastStack, provider_info: AsyncProviderInfo) -> Any:
    return provider_info["getter"](await stack.enter_async_context(provider_info["producer"]()))


def _check_for_missing_params(missing_params: HintDict) -> None:
    if missing_params:
        params_msg = ", ".join(f"{k}: {v}" for k, v in missing_params.items())
        msg = f"Missing providers for parameters: {params_msg}"
        raise InjectionError(msg)


_CURRENT_VALUES = ContextVar[Mapping[type, Any]]("CURRENT_VALUES", default={})
