from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from collections.abc import Sequence
from contextvars import ContextVar
from typing import TYPE_CHECKING
from typing import Any
from typing import ParamSpec
from typing import TypeVar

from anyio import create_task_group

from pybooster.core._private._solution import FULL_SOLUTION
from pybooster.core._private._solution import SYNC_SOLUTION
from pybooster.core._private._solution import Solution
from pybooster.core._private._utils import start_future
from pybooster.types import InjectionError

if TYPE_CHECKING:

    from pybooster.core._private._provider import AsyncProviderInfo
    from pybooster.core._private._provider import ProviderInfo
    from pybooster.core._private._provider import SyncProviderInfo
    from pybooster.core._private._utils import AsyncFastStack
    from pybooster.core._private._utils import FastStack
    from pybooster.core._private._utils import NormParamTypes


P = ParamSpec("P")
R = TypeVar("R")


def sync_inject_keywords(
    stack: FastStack,
    kwargs: dict[str, Any],
    required_params: NormParamTypes,
    fallback_values: Mapping[str, Any],
) -> None:
    missing_params = {k: required_params[k] for k in required_params.keys() - kwargs}
    inject_current_values(kwargs, missing_params)

    if not missing_params:
        return

    solution = SYNC_SOLUTION.get()
    current_values = dict(_CURRENT_VALUES.get())
    stack.push(_CURRENT_VALUES.reset, _CURRENT_VALUES.set(current_values))

    inject_given_values(kwargs, missing_params, current_values, solution)
    sync_inject_provider_values(stack, kwargs, missing_params, current_values, solution)
    inject_fallback_values(kwargs, missing_params, fallback_values)

    if missing_params:
        msg = "Missing providers for parameters: " + ", ".join(f"{k!r} with types {v}" for k, v in missing_params.items())
        raise InjectionError(msg)


async def async_inject_keywords(
    stack: AsyncFastStack,
    kwargs: dict[str, Any],
    required_params: NormParamTypes,
    fallback_values: Mapping[str, Any],
) -> None:
    missing_params = {k: required_params[k] for k in required_params.keys() - kwargs}
    inject_current_values(kwargs, missing_params)

    if not missing_params:
        return

    solution = FULL_SOLUTION.get()
    current_values = dict(_CURRENT_VALUES.get())
    stack.push(_CURRENT_VALUES.reset, _CURRENT_VALUES.set(current_values))

    inject_given_values(kwargs, missing_params, current_values, solution)
    await async_inject_provider_values(stack, kwargs, missing_params, current_values, solution)
    inject_fallback_values(kwargs, missing_params, fallback_values)

    if missing_params:
        msg = "Missing providers for parameters: " + ", ".join(f"{k!r} with types {v}" for k, v in missing_params.items())
        raise InjectionError(msg)


def inject_current_values(kwargs: dict[str, Any], missing_params: dict[str, Sequence[type]]) -> None:
    current_values = _CURRENT_VALUES.get()
    for name, types in tuple(missing_params.items()):
        for cls in types:
            if cls in current_values:
                kwargs[name] = current_values[cls]
                del missing_params[name]
                break


def inject_given_values(
    kwargs: dict[str, Any],
    missing_params: dict[str, Sequence[type]],
    current_values: dict[type, Any],
    solution: Solution
) -> None:
    for name in missing_params.keys() & kwargs:
        match types := missing_params[name]:
            case (cls,):
                current_values[cls] = kwargs[name]
                # clear any current values that are impacted by this overwrite
                for descendant_cls in solution.descendant_types(cls):
                    if descendant_cls in current_values:
                        del current_values[descendant_cls]
            case _:
                union_msg = " | ".join(t.__name__ for t in types)
                msg = f"Cannot overwrite parameter {name!r} because union {union_msg} makes it ambiguous."
                raise TypeError(msg)


def sync_inject_provider_values(
    stack: AsyncFastStack,
    kwargs: dict[str, Any],
    missing_params: NormParamTypes,
    current_values: dict[type, Any],
    solution: Solution[SyncProviderInfo]
) -> None:
    param_name_by_type = _get_param_name_by_type_map(solution, missing_params)
    for provider_generation in solution.execution_order_for(param_name_by_type.keys()):
        for provider_info in provider_generation:
            value = _sync_enter_provider_context(stack, provider_info)
            for name in param_name_by_type[cls := provider_info["provides"]]:
                kwargs[name] = current_values[cls] = value
                del missing_params[name]


async def async_inject_provider_values(
    stack: AsyncFastStack,
    kwargs: dict[str, Any],
    missing_params: dict[str, Sequence[type]],
    current_values: dict[type, Any],
    solution: Solution[ProviderInfo]
) -> None:
    param_name_by_type = _get_param_name_by_type_map(solution, missing_params)
    for provider_generation in solution.execution_order_for(param_name_by_type.keys()):
        match provider_generation:
            case [provider_info]:
                if provider_info["is_sync"]:
                    value = _sync_enter_provider_context(stack, provider_info)
                else:
                    value = await _async_enter_provider_context(stack, provider_info)
                for name in param_name_by_type[cls := provider_info["provides"]]:
                    kwargs[name] = current_values[cls] = value
                    del missing_params[name]
            case [*provider_infos]:
                async_infos: list[AsyncProviderInfo] = []
                for provider_info in provider_infos:
                    if provider_info["is_sync"]:
                        value = _sync_enter_provider_context(stack, provider_info)
                        for name in param_name_by_type[cls := provider_info["provides"]]:
                            kwargs[name] = current_values[cls] = value
                            del missing_params[name]
                    else:
                        async_infos.append(provider_info)

                async with create_task_group() as tg:
                    provider_futures = [(p, start_future(tg, _async_enter_provider_context(stack, p))) for p in async_infos]
                for p, f in provider_futures:
                    value = f()
                    for name in param_name_by_type[cls := p["provides"]]:
                        kwargs[name] = current_values[cls] = value
                        del missing_params[name]


def _get_param_name_by_type_map(solution: Solution, missing_params: NormParamTypes) -> dict[type, list[str]]:
    solution_infos = solution.infos
    param_name_by_type: defaultdict[type, list[str]] = defaultdict(list)
    for name, types in missing_params.items():
        for cls in types:
            if cls in solution_infos:
                param_name_by_type[cls].append(name)
                break
    return param_name_by_type


def inject_fallback_values(kwargs: dict[str, Any], missing_params: dict[str, Sequence[type]], fallback_values: Mapping[str, Any],) -> None:
    for name in fallback_values.keys() & missing_params:
        kwargs[name] = fallback_values[name]
        del missing_params[name]


def _sync_enter_provider_context(stack: FastStack | AsyncFastStack, provider_info: SyncProviderInfo) -> Any:
    return provider_info["getter"](stack.enter_context(provider_info["producer"]()))


async def _async_enter_provider_context(stack: AsyncFastStack, provider_info: AsyncProviderInfo) -> Any:
    return provider_info["getter"](await stack.enter_async_context(provider_info["producer"]()))


_CURRENT_VALUES = ContextVar[Mapping[type, Any]]("CURRENT_VALUES", default={})
