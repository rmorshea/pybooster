from __future__ import annotations

import builtins
from ast import TypeVarTuple
from collections.abc import AsyncIterator
from collections.abc import Coroutine
from collections.abc import Iterator
from collections.abc import Mapping
from collections.abc import Sequence
from contextlib import AbstractAsyncContextManager
from contextlib import AbstractContextManager
from inspect import Parameter
from inspect import isclass
from inspect import signature
from sys import version_info
from types import UnionType
from typing import TYPE_CHECKING
from typing import Annotated
from typing import Any
from typing import Callable
from typing import NewType
from typing import ParamSpec
from typing import TypedDict
from typing import TypeVar
from typing import Union
from typing import get_args
from typing import get_origin
from typing import get_type_hints

import pybooster

if version_info >= (3, 11):
    from typing import TypeVarTuple
else:
    from typing_extensions import TypeVarTuple

if TYPE_CHECKING:
    from anyio.abc import TaskGroup

    from pybooster.core.types import Dependencies

P = ParamSpec("P")
R = TypeVar("R")
C = TypeVar("C", bound=Callable)
D = TypeVar("D", bound=Callable)
T = TypeVarTuple("T")


def start_future(task_group: TaskGroup, coro: Coroutine[None, None, R]) -> Callable[[], R]:
    """Get a function a function that returns the result of a task once it has completed.

    The returned function raises a `RuntimeError` if the task has not completed yet.
    """
    result: R

    async def task() -> None:
        nonlocal result
        result = await coro

    task_group.start_soon(task)

    def resolve():
        try:
            return result
        except NameError:
            msg = "Promise has not completed."
            raise RuntimeError(msg) from None

    return resolve


def is_type(value: Any) -> bool:
    return get_origin(value) is not None or isclass(value) or isinstance(value, NewType)


def make_sentinel_value(module: str, name: str) -> Any:
    return type(name, (), {"__repr__": lambda _: f"{module}.{name}"})()


undefined = make_sentinel_value(__name__, "undefined")
"""Represents an undefined default."""

NormDependencies = Mapping[str, Sequence[type]]
"""Dependencies normalized to a mapping of parameter names to their possible types."""


def get_callable_dependencies(func: Callable, dependencies: Dependencies | None = None) -> NormDependencies:
    if dependencies is not None:
        return {name: cls if isinstance(cls, Sequence) else (cls,) for name, cls in dependencies.items()}
    return _get_callable_dependencies(func)


def _get_callable_dependencies(func: Callable[P, R]) -> NormDependencies:
    dependencies: dict[str, Sequence[type]] = {}
    hints = get_type_hints(func, include_extras=True)
    for param in signature(func).parameters.values():
        if param.default is pybooster.required:
            if param.kind is not Parameter.KEYWORD_ONLY:
                msg = f"Expected dependant parameter {param!r} to be keyword-only."
                raise TypeError(msg)
            dependencies[param.name] = normalize_dependency(hints[param.name])
    return dependencies


def normalize_dependency(anno: type[R] | Sequence[type[R]]) -> Sequence[type[R]]:
    if isinstance(anno, Sequence):
        return [c for cls in anno for c in normalize_dependency(cls)]

    check_is_not_builtin_type(anno)

    return normalize_dependency(get_args(anno)) if _is_union(anno) else (anno,)


def check_is_not_builtin_type(anno: Any) -> None:
    if isinstance(anno, type) and anno.__module__ == "builtins" and getattr(builtins, anno.__name__, None) is anno:
        msg = f"Cannot provide built-in type {anno.__module__}.{anno} - use NewType to make a distinct subtype."
        raise TypeError(msg)


class DependencyInfo(TypedDict):
    type: type
    new: bool


def check_is_concrete_type(cls: Any) -> None:
    if get_origin(cls) is Annotated:
        cls = get_args(cls)[0]

    if cls is Any or cls is object:
        msg = f"Can only provide concrete type, but found ambiguous type {cls}"
        raise TypeError(msg)

    for c in _recurse_type(cls):
        if type(c) is TypeVar:
            msg = f"Can only provide concrete type, but found type variable in {cls}"
            raise TypeError(msg)


def _recurse_type(cls: Any) -> Iterator[Any]:
    yield cls
    for arg in get_args(cls):
        yield from _recurse_type(arg)


def get_callable_return_type(func: Callable) -> type:
    return get_type_hints(func).get("return", Any)


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


def _is_union(anno: Any) -> bool:
    return get_origin(anno) in (Union, UnionType)


class StaticContextManager(AbstractAsyncContextManager[R], AbstractContextManager[R]):

    def __init__(self, value: R) -> None:
        self.value = value

    def __enter__(self) -> R:
        return self.value

    def __exit__(self, *args) -> None:
        pass

    async def __aenter__(self) -> R:
        return self.value

    async def __aexit__(self, *args) -> None:
        pass
