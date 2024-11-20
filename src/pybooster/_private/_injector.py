from __future__ import annotations

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

if TYPE_CHECKING:
    from pybooster._private._provider import AsyncProviderInfo
    from pybooster._private._provider import ProviderInfo
    from pybooster._private._provider import SyncProviderInfo
    from pybooster._private._utils import AsyncFastStack
    from pybooster._private._utils import FastStack
    from pybooster.types import HintDict
    from pybooster.types import HintMap


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
        _sync_inject_provider_values(
            stack, overwrite_values, missing_params, current_values, solution
        )
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
        await _async_inject_provider_values(
            stack, overwrite_values, missing_params, current_values, solution
        )
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
        if current_values.get(cls := required_params[name], undefined) is not (
            new_val := overwrite_values[name]
        ):
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
    param_name_by_type = _get_param_name_by_type_map(missing_params)
    for provider_generation in solution.execution_order_for(param_name_by_type, current_values):
        for info in provider_generation:
            current_values[info["provides"]] = _sync_enter_provider(stack, info, current_values)
    _inject_current_values(kwargs, missing_params, current_values)


async def _async_inject_provider_values(
    stack: AsyncFastStack,
    kwargs: dict[str, Any],
    missing_params: HintDict,
    current_values: dict[type, Any],
    solution: Solution[ProviderInfo],
) -> None:
    param_name_by_type = _get_param_name_by_type_map(missing_params)
    for provider_generation in solution.execution_order_for(param_name_by_type, current_values):
        match provider_generation:
            case [info]:
                if info["is_sync"] is True:
                    current_values[info["provides"]] = _sync_enter_provider(
                        stack, info, current_values
                    )
                else:
                    current_values[info["provides"]] = await _async_enter_provider(
                        stack, info, current_values
                    )
            case _:
                async_infos: list[AsyncProviderInfo] = []
                for info in provider_generation:
                    if info["is_sync"] is True:
                        current_values[info["provides"]] = _sync_enter_provider(
                            stack, info, current_values
                        )
                    else:
                        async_infos.append(info)
                if async_infos:
                    async with create_task_group() as tg:
                        provider_futures = [
                            (
                                i["provides"],
                                start_future(tg, _async_enter_provider(stack, i, current_values)),
                            )
                            for i in async_infos
                        ]
                    for cls, f_result in provider_futures:
                        current_values[cls] = f_result()
    _inject_current_values(kwargs, missing_params, current_values)


def _get_param_name_by_type_map(missing_params: HintMap) -> dict[type, list[str]]:
    param_name_by_type: dict[type, list[str]] = {}
    for name, cls in missing_params.items():
        if cls not in param_name_by_type:
            param_name_by_type[cls] = [name]
        else:
            param_name_by_type[cls].append(name)
    return param_name_by_type


def _sync_enter_provider(
    stack: FastStack | AsyncFastStack,
    info: SyncProviderInfo,
    current_values: Mapping[type, Any],
) -> Any:
    kwargs = {n: current_values[c] for n, c in info["required_parameters"].items()}
    return info["getter"](stack.enter_context(info["producer"](**kwargs)))


async def _async_enter_provider(
    stack: AsyncFastStack,
    info: AsyncProviderInfo,
    current_values: Mapping[type, Any],
) -> Any:
    kwargs = {n: current_values[c] for n, c in info["required_parameters"].items()}
    return info["getter"](await stack.enter_async_context(info["producer"](**kwargs)))


_CURRENT_VALUES = ContextVar[Mapping[type, Any]]("CURRENT_VALUES", default={})
