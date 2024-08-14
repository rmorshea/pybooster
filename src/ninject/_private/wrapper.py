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
from ninject._private.scope import get_scope_provider
from ninject._private.utils import async_exhaust_exits
from ninject._private.utils import exhaust_exits

P = ParamSpec("P")
R = TypeVar("R")


def make_injection_wrapper(func: Callable[P, R], dependencies: Mapping[str, type]) -> Callable[P, R]:
    if not dependencies:
        return func

    wrapper: Callable[..., Any]
    if isasyncgenfunction(func):

        async def async_gen_wrapper(*args: Any, **kwargs: Any) -> Any:
            contexts: list[Scope] = []

            try:
                for name in dependencies.keys() - kwargs.keys():
                    cls = dependencies[name]
                    context = get_scope_provider(cls)()
                    kwargs[name] = await context.__aenter__()
                    contexts.append(context)
                async for value in func(*args, **kwargs):
                    yield value
            finally:
                await async_exhaust_exits(contexts)

        wrapper = async_gen_wrapper

    elif isgeneratorfunction(func):

        def sync_gen_wrapper(*args: Any, **kwargs: Any) -> Any:
            contexts: list[Scope] = []
            try:
                for name in dependencies.keys() - kwargs.keys():
                    cls = dependencies[name]
                    context = get_scope_provider(cls)()
                    kwargs[name] = context.__enter__()
                    contexts.append(context)
                yield from func(*args, **kwargs)
            finally:
                exhaust_exits(contexts)

        wrapper = sync_gen_wrapper

    elif iscoroutinefunction(func):

        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            contexts: list[Scope] = []

            try:
                for name in dependencies.keys() - kwargs.keys():
                    cls = dependencies[name]
                    context = get_scope_provider(cls)()
                    kwargs[name] = await context.__aenter__()
                    contexts.append(context)
                return await func(*args, **kwargs)
            finally:
                await async_exhaust_exits(contexts)

        wrapper = async_wrapper

    elif isfunction(func):

        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            contexts: list[Scope] = []
            try:
                for name in dependencies.keys() - kwargs.keys():
                    cls = dependencies[name]
                    context = get_scope_provider(cls)()
                    kwargs[name] = context.__enter__()
                    contexts.append(context)
                return func(*args, **kwargs)
            finally:
                exhaust_exits(contexts)

        wrapper = sync_wrapper

    else:
        msg = f"Unsupported function type: {func}"
        raise TypeError(msg)

    return cast(Callable[P, R], wraps(cast(Callable, func))(wrapper))
