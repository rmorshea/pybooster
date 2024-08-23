from asyncio import iscoroutinefunction
from collections.abc import Mapping
from functools import wraps
from inspect import isasyncgenfunction
from inspect import isfunction
from inspect import isgeneratorfunction
from typing import Any
from typing import Callable
from typing import ParamSpec
from typing import TypeVar
from typing import cast

from ninject._private.scope import Scope
from ninject._private.scope import get_scope_constructor
from ninject._private.utils import async_exhaust_exits
from ninject._private.utils import exhaust_exits

P = ParamSpec("P")
R = TypeVar("R")


def make_injection_wrapper(
    func: Callable[P, R],
    dependencies: Mapping[str, type],
    defaults: Mapping[str, Any],
) -> Callable[P, R]:
    if not dependencies:
        return func

    wrapper: Callable[..., Any]
    if isasyncgenfunction(func):

        async def async_gen_wrapper(*args: Any, **kwargs: Any) -> Any:
            scopes: list[Scope] = []
            try:
                await _async_init_scopes(dependencies, defaults, kwargs, scopes)
                async for value in func(*args, **kwargs):
                    yield value
            finally:
                await async_exhaust_exits(scopes)

        wrapper = async_gen_wrapper

    elif isgeneratorfunction(func):

        def sync_gen_wrapper(*args: Any, **kwargs: Any) -> Any:
            scopes: list[Scope] = []
            try:
                _sync_init_scopes(dependencies, defaults, kwargs, scopes)
                yield from func(*args, **kwargs)
            finally:
                exhaust_exits(scopes)

        wrapper = sync_gen_wrapper

    elif iscoroutinefunction(func):

        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            scopes: list[Scope] = []
            try:
                await _async_init_scopes(dependencies, defaults, kwargs, scopes)
                return await func(*args, **kwargs)
            finally:
                await async_exhaust_exits(scopes)

        wrapper = async_wrapper

    elif isfunction(func):

        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            scopes: list[Scope] = []
            try:
                _sync_init_scopes(dependencies, defaults, kwargs, scopes)
                return func(*args, **kwargs)
            finally:
                exhaust_exits(scopes)

        wrapper = sync_wrapper

    else:
        msg = f"Unsupported function type: {func}"
        raise TypeError(msg)

    return cast(Callable[P, R], wraps(cast(Callable, func))(wrapper))


def _sync_init_scopes(
    dependencies: Mapping[str, type],
    defaults: Mapping[str, Any],
    kwargs: dict[str, Any],
    scopes: list[Scope],
) -> None:
    for name in dependencies.keys() - kwargs.keys():
        cls = dependencies[name]
        try:
            scope_provider = get_scope_constructor(cls)
        except RuntimeError:
            if name not in defaults:
                raise
            value = defaults[name]
        else:
            scope = scope_provider()
            value = scope.__enter__()
            scopes.append(scope)
        kwargs[name] = value


async def _async_init_scopes(
    dependencies: Mapping[str, type],
    defaults: Mapping[str, Any],
    kwargs: dict[str, Any],
    scopes: list[Scope],
) -> None:
    for name in dependencies.keys() - kwargs.keys():
        cls = dependencies[name]
        try:
            scope_provider = get_scope_constructor(cls)
        except RuntimeError:
            if name not in defaults:
                raise
            value = defaults[name]
        else:
            scope = scope_provider()
            value = await scope.__aenter__()
            scopes.append(scope)
        kwargs[name] = value
