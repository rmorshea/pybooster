from __future__ import annotations

import builtins
from collections.abc import AsyncIterator
from collections.abc import Awaitable
from collections.abc import Callable
from collections.abc import Coroutine
from collections.abc import Iterator
from collections.abc import Mapping
from collections.abc import Sequence
from contextlib import AbstractAsyncContextManager
from contextlib import AbstractContextManager
from dataclasses import dataclass
from inspect import Parameter
from inspect import isclass
from inspect import signature
from sys import exc_info
from types import resolve_bases
from typing import TYPE_CHECKING
from typing import Annotated
from typing import Any
from typing import Literal
from typing import NewType
from typing import ParamSpec
from typing import TypedDict
from typing import TypeVar
from typing import TypeVarTuple
from typing import Union
from typing import dataclass_transform
from typing import get_args
from typing import get_origin
from typing import get_type_hints

import pybooster

if TYPE_CHECKING:
    from anyio.abc import TaskGroup

    from pybooster.types import HintMap

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


def get_class_lineage(obj: Any) -> Sequence[type]:
    """Get a sequence of classes that the given object is an instance of."""
    if hasattr(obj, "__mro__"):
        return obj.__mro__
    elif isinstance(obj, NewType):
        return (obj, *get_class_lineage(obj.__supertype__))
    else:
        return (obj, *resolve_bases((obj,)))


undefined = make_sentinel_value(__name__, "undefined")
"""Represents an undefined default."""


class FallbackMarker:
    def __init__(self, value: Any) -> None:
        self.value = value


def get_required_parameters(func: Callable, dependencies: HintMap = None) -> HintMap:
    return dependencies if dependencies is not None else _get_required_parameters(func)


def get_fallback_parameters(func: Callable, fallbacks: Mapping[str, Any] | None = None) -> dict[str, Any]:
    return (
        fallbacks
        if fallbacks is not None
        else {
            param.name: param.default.value
            for param in signature(func).parameters.values()
            if isinstance(param.default, FallbackMarker)
        }
    )


def _get_required_parameters(func: Callable[P, R]) -> HintMap:
    required_params: dict[str, type] = {}
    hints = get_type_hints(func, include_extras=True)
    for param in signature(func).parameters.values():
        if param.default is pybooster.required or isinstance(param.default, FallbackMarker):
            if param.kind is not Parameter.KEYWORD_ONLY:
                msg = f"Expected dependant parameter {param!r} to be keyword-only."
                raise TypeError(msg)
            check_is_valid_dependency_type(param_hint := hints[param.name])
            required_params[param.name] = param_hint
    return required_params


def check_is_valid_dependency_type(anno: Any) -> None:
    anno = strip_annotated(anno)
    check_is_not_builtin_type(anno)
    check_is_not_union_type(anno)


def check_is_not_union_type(anno: Any) -> None:
    if get_origin(strip_annotated(anno)) is Union:
        msg = f"Cannot use Union type {anno} as a dependency."
        raise TypeError(msg)


def strip_annotated(anno: Any) -> Any:
    return get_args(anno)[0] if get_origin(anno) is Annotated else anno


def check_is_not_builtin_type(anno: Any) -> None:
    if is_builtin_type(get_origin(strip_annotated(anno)) or anno):
        msg = (
            f"Cannot use built-in type {anno.__module__}.{anno} as a dependency"
            " - use NewType to make a distinct subtype."
        )
        raise TypeError(msg)


def is_builtin_type(anno: Any) -> bool:
    return anno is None or (
        isinstance(anno, type) and anno.__module__ == "builtins" and getattr(builtins, anno.__name__, None) is anno
    )


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
    hint = get_type_hints(func, include_extras=True).get("return", Any)
    check_is_not_builtin_type(hint)
    check_is_not_union_type(hint)
    return hint


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


class StaticContextManager(AbstractAsyncContextManager[R], AbstractContextManager[R]):

    def __init__(self, value: R) -> None:
        self.value = value

    def __enter__(self) -> R:
        return self.value

    def __exit__(self, *_) -> None:
        pass

    async def __aenter__(self) -> R:
        return self.value

    async def __aexit__(self, *args) -> None:
        pass


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

    Part of the reason this is faster is because it does not simulate nested with statements.
    """

    def close(self) -> None:
        if cb_len := len(self._callbacks):
            _sync_unravel_stack(self._callbacks, cb_len - 1)


class AsyncFastStack(_FastStack):
    """A more performant alternative to using `contextlib.AsyncExitStack` for callbacks.

    Users must call `aclose` to ensure all callbacks are called.

    Part of the reason this is faster is because it does not simulate nested with statements.
    """

    def push_async_callback(self, func: Callable[P, Awaitable], *args: P.args, **kwargs: P.kwargs) -> None:
        self._callbacks.append((True, func, args, kwargs))

    async def enter_async_context(self, context: AbstractAsyncContextManager[R]) -> R:
        result = await context.__aenter__()
        self._callbacks.append((True, context.__aexit__))
        return result

    async def aclose(self) -> None:
        if cb_len := len(self._callbacks):
            await _async_unravel_stack(self._callbacks, cb_len - 1)


def _sync_unravel_stack(callbacks: Sequence[_Callback], position: int) -> None:
    try:
        match callbacks[position]:
            case [False, func, args, kwargs]:
                func(*args, **kwargs)
            case [False, exit]:
                exit(*exc_info())
            case _:
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
            case _:
                msg = "Unexpected callback type"
                raise AssertionError(msg)
    finally:
        if position > 0:
            await _async_unravel_stack(callbacks, position - 1)


@dataclass_transform(frozen_default=True, kw_only_default=True)
def frozenclass(cls: type[R]) -> type[R]:
    return dataclass(frozen=True, kw_only=True)(cls)
