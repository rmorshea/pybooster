from __future__ import annotations

from collections.abc import AsyncIterator
from collections.abc import Coroutine
from collections.abc import Iterator
from contextlib import AbstractAsyncContextManager
from contextlib import AbstractContextManager
from functools import wraps
from inspect import Parameter
from inspect import isclass
from inspect import signature
from typing import TYPE_CHECKING
from typing import Annotated
from typing import Any
from typing import Callable
from typing import Concatenate
from typing import ParamSpec
from typing import Protocol
from typing import TypedDict
from typing import TypeVar
from typing import get_args
from typing import get_origin
from typing import get_type_hints
from typing import overload

import ninject

if TYPE_CHECKING:
    from collections.abc import Mapping

P = ParamSpec("P")
R = TypeVar("R")
C = TypeVar("C", bound=Callable)
D = TypeVar("D", bound=Callable)


def make_sentinel_value(module: str, name: str) -> Any:
    return type(name, (), {"__repr__": lambda _: f"{module}.{name}"})()


transient = make_sentinel_value(__name__, "transient")
"""Represents a transient dependency - one that should be re-initialized each time it is requested."""

undefined = make_sentinel_value(__name__, "undefined")
"""Represents an undefined default."""


def get_transient_and_singleton_dependencies(
    dependencies: Mapping[str, type],
) -> tuple[dict[str, type], dict[str, type]]:
    transient_dependencies: dict[str, type] = {}
    singleton_dependencies: dict[str, type] = {}
    for name, cls in dependencies.items():
        if _is_transient_dependency(cls):
            anno, *_ = get_args(cls)
            transient_dependencies[name] = anno
        else:
            singleton_dependencies[name] = cls
    return transient_dependencies, singleton_dependencies


def get_dependencies(func: Callable, dependencies: Mapping[str, type] | None = None) -> Mapping[str, type]:
    if dependencies is not None:
        return dependencies
    return _get_callable_dependencies(func)


def _is_transient_dependency(cls: type) -> bool:
    return get_origin(cls) is Annotated and transient in get_args(cls)


def _get_callable_dependencies(func: Callable[P, R]) -> dict[str, type]:
    dependencies: dict[str, type] = {}
    hints = get_type_hints(func, include_extras=True)
    for param in signature(func).parameters.values():
        if param.default is ninject.required:
            if param.kind is not Parameter.KEYWORD_ONLY:
                msg = f"Expected dependant parameter {param!r} to be keyword-only."
                raise TypeError(msg)
            dependencies[param.name] = hints[param.name]
    return dependencies


class DependencyInfo(TypedDict):
    type: type
    new: bool


def decorator(deco: Callable[Concatenate[C, P], D]) -> Decorator[C, P, D]:
    """Create an optionally parameterized decorator."""

    @wraps(deco)
    def wrapper(func: C = undefined, /, *args: P.args, **kwargs: P.kwargs) -> Callable[[C], D] | D:
        if func is undefined:
            return lambda func: deco(func, *args, **kwargs)
        else:
            return deco(func, *args, **kwargs)

    return wrapper


class Decorator(Protocol[C, P, D]):
    """An optionally parameterized decorator protocol."""

    @overload
    def __call__(self, func: None = ..., /, *args: P.args, **kwargs: P.kwargs) -> Callable[[C], D]: ...

    @overload
    def __call__(self, func: C, /, *args: P.args, **kwargs: P.kwargs) -> D: ...

    def __call__(self, func: C = ..., /, *args: P.args, **kwargs: P.kwargs) -> Callable[[C], D] | D: ...


class AsyncCompatContextManager(AbstractAsyncContextManager[R]):
    def __init__(self, manager: AbstractContextManager[R]):
        self._manager = manager

    async def __aenter__(self) -> R:
        return self._manager.__enter__()

    async def __aexit__(self, *args: Any) -> None:
        self._manager.__exit__(*args)


def get_callable_return_type(func: Callable) -> type:
    hints = get_type_hints(func)

    if (return_type := hints.get("return")) is None:
        msg = f"Expected function {func} to have a return type"
        raise TypeError(msg)

    return return_type


def get_coroutine_return_type(func: Callable) -> type:
    return_type = get_callable_return_type(func)
    if get_origin(return_type) is Coroutine:
        try:
            return get_args(return_type)[2]
        except IndexError:
            msg = f"Expected return type {return_type} to have three arguments"
            raise TypeError(msg) from None
    else:
        return return_type


def get_iterator_yield_type(func: Callable, *, sync: bool) -> type:
    return_type = get_callable_return_type(func)
    if sync:
        if get_origin(return_type) is not Iterator:
            msg = f"Expected return type {return_type} to be an iterator"
            raise TypeError(msg)
    else:
        if get_origin(return_type) is not AsyncIterator:
            msg = f"Expected return type {return_type} to be an async iterator"
            raise TypeError(msg)
    try:
        return get_args(return_type)[0]
    except IndexError:
        msg = f"Expected return type {return_type} to have a single argument"
        raise TypeError(msg) from None


def get_context_manager_yield_type(func_or_cls: Callable, *, sync: bool) -> type:
    if not isclass(func_or_cls):
        msg = f"Could not determine yield type for {func_or_cls} - declare it explicitly with the 'yields' parameter"
        raise TypeError(msg)
    enter_method_name = "__enter__" if sync else "__aenter__"
    enter_method = getattr(func_or_cls, enter_method_name, None)
    if enter_method is None:
        msg = f"Expected class {func_or_cls} to have method {enter_method_name!r}"
        raise TypeError(msg)
    return (get_callable_return_type if sync else get_coroutine_return_type)(enter_method)
