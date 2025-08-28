from __future__ import annotations

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
from pybooster.types import Hint

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


def sync_inject_into_params(
    stack: FastStack,
    param_vals: dict[str, Any],
    param_deps: HintMap,
    *,
    set_scope: bool = False,
) -> None:
    """Inject missing dependencies and overwrite the current scope with any given.

    Args:
        stack:
            An exit stack to attach callbacks that clean up any values that were injected for the
            requested dependencies. The caller must close the stack later. When they do, injected
            values will be cleaned up.
        param_vals:
            A dict of parameter names to their values into which values for missing dependencies
            (defined by `param_deps`) will be injected. Any prepopulated values in this dictionary
            will be used to overwrite the values of any corresponding dependencies.
        param_deps:
            A mapping of parameter names to their dependencies. All parameter names in `param_vals`
            must be present in `param_deps`.
        set_scope:
            By default, values generated to fulfill missing dependencies will not survive this call.
            That is they will be generated once and then will not be saved in the current scope.
            Setting this to `True` will allow those values to persist in the current scope until
            the `stack` is closed.

    Examples:
        Injecting values into parameters:

        ```python
        from typing import NewType
        from pybooster import solution
        from pybooster import provider
        from pybooster import get_scope
        from pybooster._private._utils import FastStack
        from pybooster._private._injector import sync_inject_into_params

        Username = NewType("Username", str)
        Password = NewType("Password", str)


        @provider.function
        def provide_username() -> Username:
            return Username("bob")


        with solution(provide_username):
            stack = FastStack()

            param_vals = {"pw": "monkey123"}
            param_deps = {"un": Username, "pw": Password}
            sync_inject_into_params(
                stack,
                param_vals,
                param_deps,
            )
            assert param_vals == {"un": "bob", "pw": "monkey123"}

            # no current values because set_scope=False
            assert get_scope() == {}

            sync_inject_into_params(
                stack,
                param_vals,
                param_deps,
                set_scope=True,
            )
            assert param_vals == {"un": "bob", "pw": "monkey123"}

            # current values persist because set_scope=True
            assert get_scope() == {Username: "bob", Password: "monkey123"}

            stack.close()

            # Current values are cleared after the stack is closed
            assert get_scope() == {}
        ```
    """
    solution = SYNC_SOLUTION.get()
    current_values = dict(_CURRENT_VALUES.get())

    _inject_params_into_current_values(param_vals, param_deps, current_values, solution)
    missing_params = {k: param_deps[k] for k in param_deps.keys() - param_vals}
    _inject_current_values_into_params(param_vals, missing_params, current_values)

    if not missing_params:
        if set_scope:
            stack.push_callback(_CURRENT_VALUES.reset, _CURRENT_VALUES.set(current_values))
        return

    current_values_token = _CURRENT_VALUES.set(current_values)
    try:
        _sync_inject_from_provider_values(
            stack, param_vals, missing_params, current_values, solution
        )
    finally:
        if set_scope:
            stack.push_callback(_CURRENT_VALUES.reset, current_values_token)
        else:
            _CURRENT_VALUES.reset(current_values_token)


async def async_inject_into_params(
    stack: AsyncFastStack,
    param_vals: dict[str, Any],
    param_deps: HintMap,
    *,
    set_scope: bool = False,
) -> None:
    """Inject missing dependencies and overwrite the current scope with any given.

    Args:
        stack:
            An exit stack to attach callbacks that clean up any values that were injected for the
            requested dependencies. The caller must close the stack later. When they do, injected
            values will be cleaned up.
        param_vals:
            A dict of parameter names to their values into which values for missing dependencies
            (defined by `param_deps`) will be injected. Any prepopulated values in this dictionary
            will be used to overwrite the values of any corresponding dependencies.
        param_deps:
            A mapping of parameter names to their dependencies. All parameter names in `param_vals`
            must be present in `param_deps`.
        set_scope:
            By default, values generated to fulfill missing dependencies will not survive this call.
            That is they will be generated once and then will not be saved in the current scope.
            Setting this to `True` will allow those values to persist in the current scope until
            the `stack` is closed.

    Examples:
        ```python
        import asyncio

        from typing import NewType
        from pybooster import solution
        from pybooster import provider
        from pybooster import get_scope
        from pybooster._private._utils import AsyncFastStack
        from pybooster._private._injector import async_inject_into_params

        Username = NewType("Username", str)
        Password = NewType("Password", str)


        @provider.function
        def provide_username() -> Username:
            return Username("bob")


        async def main():
            with solution(provide_username):
                stack = AsyncFastStack()

                param_vals = {"pw": "monkey123"}
                param_deps = {"un": Username, "pw": Password}
                await async_inject_into_params(
                    stack,
                    param_vals,
                    param_deps,
                )
                assert param_vals == {"un": "bob", "pw": "monkey123"}

                # no current values because set_scope=False
                assert get_scope() == {}

                await async_inject_into_params(
                    stack,
                    param_vals,
                    param_deps,
                    set_scope=True,
                )
                assert param_vals == {"un": "bob", "pw": "monkey123"}

                # current values persist because set_scope=True
                assert get_scope() == {Username: "bob", Password: "monkey123"}

                await stack.aclose()

                # Current values are cleared after the stack is closed
                assert get_scope() == {}


        asyncio.run(main())
        ```
    """
    solution = FULL_SOLUTION.get()
    current_values = dict(_CURRENT_VALUES.get())

    _inject_params_into_current_values(param_vals, param_deps, current_values, solution)
    missing_params = {k: param_deps[k] for k in param_deps.keys() - param_vals}
    _inject_current_values_into_params(param_vals, missing_params, current_values)

    if not missing_params:
        if set_scope:
            stack.push_callback(_CURRENT_VALUES.reset, _CURRENT_VALUES.set(current_values))
        return

    current_values_token = _CURRENT_VALUES.set(current_values)
    try:
        await _async_inject_from_provider_values(
            stack, param_vals, missing_params, current_values, solution
        )
    finally:
        if set_scope:
            stack.push_callback(_CURRENT_VALUES.reset, current_values_token)
        else:
            _CURRENT_VALUES.reset(current_values_token)


def _inject_params_into_current_values(
    param_vals: dict[str, Any],
    param_deps: HintMap,
    current_values: dict[Hint, Any],
    solution: Solution,
) -> None:
    to_update: dict[Hint, Any] = {}
    to_invalidate: set[Hint] = set()
    for name in param_deps.keys() & param_vals:
        cls = param_deps[name]
        if current_values.get(cls, undefined) is not (new_val := param_vals[name]):
            to_invalidate.update(solution.descendant_types(cls))
            to_update[cls] = new_val
    for cls in (
        # don't invalidate anything we're going to update
        to_invalidate - to_update.keys()
    ):
        current_values.pop(cls, None)
    current_values.update(to_update)


def _inject_current_values_into_params(
    param_vals: dict[str, Any],
    missing_params: HintDict,
    current_values: Mapping[Hint, Any],
) -> None:
    for name, cls in tuple(missing_params.items()):
        if cls in current_values:
            param_vals[name] = current_values[cls]
            del missing_params[name]


def _sync_inject_from_provider_values(
    stack: FastStack,
    param_vals: dict[str, Any],
    missing_params: HintDict,
    current_values: dict[Hint, Any],
    solution: Solution[SyncProviderInfo],
) -> None:
    for exe_group in solution.execution_order_for(missing_params.values(), current_values):
        for prov in exe_group:
            current_values[prov["provides"]] = _sync_enter_provider(stack, prov, current_values)
    _inject_current_values_into_params(param_vals, missing_params, current_values)


async def _async_inject_from_provider_values(
    stack: AsyncFastStack,
    param_vals: dict[str, Any],
    missing_params: HintDict,
    current_values: dict[Hint, Any],
    solution: Solution[ProviderInfo],
) -> None:
    for exe_group in solution.execution_order_for(missing_params.values(), current_values):
        match exe_group:
            case [prov]:
                if prov["is_sync"] is True:
                    current_values[prov["provides"]] = _sync_enter_provider(
                        stack, prov, current_values
                    )
                else:
                    current_values[prov["provides"]] = await _async_enter_provider(
                        stack, prov, current_values
                    )
            case _:
                async_provs: list[AsyncProviderInfo] = []
                for prov in exe_group:
                    if prov["is_sync"] is True:
                        current_values[prov["provides"]] = _sync_enter_provider(
                            stack, prov, current_values
                        )
                    else:
                        async_provs.append(prov)
                match async_provs:
                    case []:
                        pass
                    case [prov]:
                        current_values[prov["provides"]] = await _async_enter_provider(
                            stack, prov, current_values
                        )
                    case _:
                        async with create_task_group() as tg:
                            provider_futures = [
                                (
                                    p,
                                    start_future(
                                        tg, _async_enter_provider(stack, p, current_values)
                                    ),
                                )
                                for p in async_provs
                            ]
                        for prov, result in provider_futures:
                            current_values[prov["provides"]] = result()
    _inject_current_values_into_params(param_vals, missing_params, current_values)


def _sync_enter_provider(
    stack: FastStack | AsyncFastStack,
    info: SyncProviderInfo,
    current_values: Mapping[Hint, Any],
) -> Any:
    kwargs = {n: current_values[c] for n, c in info["required_parameters"].items()}
    return info["getter"](stack.enter_context(info["producer"](**kwargs)))


async def _async_enter_provider(
    stack: AsyncFastStack,
    info: AsyncProviderInfo,
    current_values: Mapping[Hint, Any],
) -> Any:
    kwargs = {n: current_values[c] for n, c in info["required_parameters"].items()}
    return info["getter"](await stack.enter_async_context(info["producer"](**kwargs)))


_CURRENT_VALUES = ContextVar[Mapping[Hint, Any]]("CURRENT_VALUES", default={})
