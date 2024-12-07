from __future__ import annotations

import builtins
from collections.abc import AsyncIterator
from collections.abc import Awaitable
from collections.abc import Callable
from collections.abc import Coroutine
from collections.abc import Iterator
from collections.abc import Mapping
from collections.abc import Sequence
from dataclasses import dataclass
from inspect import Parameter
from inspect import isclass
from inspect import signature
from sys import exc_info
from typing import TYPE_CHECKING
from typing import Annotated
from typing import Any
from typing import Literal
from typing import NewType
from typing import ParamSpec
from typing import TypedDict
from typing import TypeVar
from typing import Union
from typing import dataclass_transform
from typing import get_args
from typing import get_origin
from typing import get_type_hints

from typing_extensions import TypeIs

import pybooster

if TYPE_CHECKING:
    from contextlib import AbstractAsyncContextManager
    from contextlib import AbstractContextManager

    from anyio.abc import TaskGroup

    from pybooster.types import Hint
    from pybooster.types import HintMap
    from pybooster.types import HintSeq

P = ParamSpec("P")
R = TypeVar("R")


RawAnnotation = NewType("RawAnnotation", object)
"""A type annotation without any "extras" (e.g. `Annotated` metadata)."""


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


def is_type(value: Any) -> TypeIs[type]:
    return get_origin(value) is not None or isclass(value) or isinstance(value, NewType)


def make_sentinel_value(module: str, name: str) -> Any:
    return type(name, (), {"__repr__": lambda _: f"{module}.{name}"})()


undefined = make_sentinel_value(__name__, "undefined")
"""Represents an undefined default."""


def get_required_parameters(
    func: Callable, dependencies: HintMap | HintSeq | None = None
) -> HintMap:
    match dependencies:
        case None:
            return _get_required_parameter_types(func)
        case Mapping():
            params = _get_required_sig_parameters(func)
            if (lpar := len(params)) > (ldep := len(dependencies)):
                msg = f"Could not match {ldep} dependencies to {lpar} required parameters."
                raise TypeError(msg)
            return dependencies
        case Sequence():
            params = _get_required_sig_parameters(func)
            if (lpar := len(params)) > (ldep := len(dependencies)):
                msg = f"Could not match {ldep} dependencies to {lpar} required parameters."
                raise TypeError(msg)
            return dict(zip((p.name for p in params), dependencies, strict=False))
        case _:  # nocov
            msg = f"Expected a mapping or sequence of dependencies, but got {dependencies!r}."
            raise TypeError(msg)


def _get_required_parameter_types(func: Callable[P, R]) -> HintMap:
    required_params: dict[str, Hint] = {}
    hints = get_type_hints(func, include_extras=True)
    for param in _get_required_sig_parameters(func):
        check_is_required_type(hint := hints[param.name])
        required_params[param.name] = hint
    return required_params


def _get_required_sig_parameters(func: Callable[P, R]) -> list[Parameter]:
    params: list[Parameter] = []
    for p in signature(func).parameters.values():
        if p.default is pybooster.required:
            if p.kind is not Parameter.KEYWORD_ONLY:
                msg = f"Expected dependant parameter {p!r} to be keyword-only."
                raise TypeError(msg)
            params.append(p)
    return params


def get_raw_annotation(anno: Any) -> RawAnnotation:
    return RawAnnotation(get_args(anno)[0] if get_origin(anno) is Annotated else anno)


def check_is_required_type(anno: Any) -> Any:
    raw_anno = get_raw_annotation(anno)
    check_is_not_builtin_type(raw_anno)
    check_is_not_union_type(raw_anno)
    return anno


def check_is_not_union_type(anno: RawAnnotation) -> None:
    if get_origin(get_raw_annotation(anno)) is Union:
        msg = f"Cannot use Union type {anno} as a dependency."
        raise TypeError(msg)


def check_is_not_builtin_type(anno: RawAnnotation) -> None:
    if get_origin(anno) is tuple and (tuple_args := get_args(anno)):
        for a in tuple_args:
            check_is_not_builtin_type(a)
    elif is_builtin_type(anno):
        msg = (
            f"Cannot use built-in type {anno.__module__}.{anno} as a dependency"
            " - use NewType to make a distinct subtype."
        )
        raise TypeError(msg)


def is_builtin_type(anno: RawAnnotation) -> bool:
    final_anno = get_origin(anno) if get_args(anno) else anno
    return final_anno is None or (
        isinstance(final_anno, type)
        and final_anno.__module__ == "builtins"
        and getattr(builtins, final_anno.__name__, None) is final_anno
    )


class DependencyInfo(TypedDict):
    type: Hint
    new: bool


def check_is_concrete_type(cls: RawAnnotation) -> None:
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


def get_callable_return_type(func: Callable) -> Hint:
    anno = get_type_hints(func, include_extras=True).get("return", Any)
    raw_anno = get_raw_annotation(anno)
    check_is_not_builtin_type(raw_anno)
    return anno


def get_coroutine_return_type(func: Callable) -> Hint:
    return_type = get_callable_return_type(func)
    if get_origin(return_type) is Coroutine:
        try:
            return get_args(return_type)[2]
        except IndexError:
            msg = f"Expected return type {return_type} to have three arguments"
            raise TypeError(msg) from None
    else:
        return return_type


def get_iterator_yield_type(func: Callable, *, sync: bool) -> Hint:
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


_Callback = (
    # sync callback
    tuple[Literal[False], Callable[..., Any], tuple, dict]
    # sync exit callback
    | tuple[Literal[False], Callable[[Any, Any, Any], Any]]
    # async callback
    | tuple[Literal[True], Callable[..., Awaitable], tuple, dict]
    # async exit callback
    | tuple[Literal[True], Callable[[Any, Any, Any], Awaitable]]
)


class _FastStack:
    def __init__(self) -> None:
        self._callbacks: list[_Callback] = []

    def push_callback(self, func: Callable[P, Any], *args: P.args, **kwargs: P.kwargs) -> None:
        self._callbacks.append((False, func, args, kwargs))

    def enter_context(self, context: AbstractContextManager[R]) -> R:
        result = context.__enter__()
        self._callbacks.append((False, context.__exit__))
        return result


class FastStack(_FastStack):
    """A more performant alternative to using `contextlib.ExitStack` for callbacks.

    Users must call `close` to ensure all callbacks are called.
    """

    def close(self) -> None:
        if cb_len := len(self._callbacks):
            try:
                _sync_unravel_stack(self._callbacks, cb_len - 1)
            finally:
                self._callbacks.clear()


class AsyncFastStack(_FastStack):
    """A more performant alternative to using `contextlib.AsyncExitStack` for callbacks.

    Users must call `aclose` to ensure all callbacks are called.
    """

    def push_async_callback(
        self, func: Callable[P, Awaitable], *args: P.args, **kwargs: P.kwargs
    ) -> None:
        self._callbacks.append((True, func, args, kwargs))

    async def enter_async_context(self, context: AbstractAsyncContextManager[R]) -> R:
        result = await context.__aenter__()
        self._callbacks.append((True, context.__aexit__))
        return result

    async def aclose(self) -> None:
        if cb_len := len(self._callbacks):
            try:
                await _async_unravel_stack(self._callbacks, cb_len - 1)
            finally:
                self._callbacks.clear()


def _sync_unravel_stack(callbacks: Sequence[_Callback], position: int) -> None:
    try:
        match callbacks[position]:
            case [False, func, args, kwargs]:
                func(*args, **kwargs)
            case [False, exit]:
                exit(*exc_info())
            case _:  # nocov
                msg = "Unexpected callback type"
                raise AssertionError(msg)
    finally:
        if position > 0:
            _sync_unravel_stack(callbacks, position - 1)


async def _async_unravel_stack(callbacks: Sequence[_Callback], position: int) -> None:
    try:
        match callbacks[position]:
            case [True, func, args, kwargs]:
                await func(*args, **kwargs)
            case [False, func, args, kwargs]:
                func(*args, **kwargs)
            case [True, exit]:
                await exit(*exc_info())
            case [False, exit]:
                exit(*exc_info())
            case _:  # nocov
                msg = "Unexpected callback type"
                raise AssertionError(msg)
    finally:
        if position > 0:
            await _async_unravel_stack(callbacks, position - 1)


@dataclass_transform(frozen_default=True, kw_only_default=True)
def frozenclass(cls: type[R]) -> type[R]:
    """Returm a frozen dataclass."""
    return dataclass(frozen=True, kw_only=True)(cls)
