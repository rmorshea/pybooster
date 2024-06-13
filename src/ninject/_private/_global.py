from __future__ import annotations

from contextvars import ContextVar
from typing import Any, Callable, ParamSpec, TypeVar, cast
from weakref import WeakKeyDictionary

from ninject._private._contexts import UniformContextProvider

P = ParamSpec("P")
R = TypeVar("R")


INJECTED = cast(Any, (type("INJECTED", (), {"__repr__": lambda _: "INJECTED"}))())


def add_dependency(cls: type) -> None:
    _DEPENDENCIES.add(cls)


def has_dependency(cls: type) -> bool:
    return cls in _DEPENDENCIES


def set_context_provider(cls: type[R], provider: UniformContextProvider[R]) -> Callable[[], None]:
    if not (context_provider_var := _CONTEXT_PROVIDER_VARS_BY_TYPE.get(cls)):
        context_provider_var = _CONTEXT_PROVIDER_VARS_BY_TYPE[cls] = ContextVar(f"{cls.__name__}_provider")

    token = context_provider_var.set(provider)
    return lambda: context_provider_var.reset(token)


def get_context_provider(cls: type[R]) -> UniformContextProvider[R]:
    try:
        context_provider_var = _CONTEXT_PROVIDER_VARS_BY_TYPE[cls]
    except KeyError:
        msg = f"No provider declared for {cls}"
        raise RuntimeError(msg) from None
    return context_provider_var.get()


def setdefault_context_var(cls: type[R]) -> ContextVar:
    if not (context_var := _DEPENDENCY_VARS_BY_TYPE.get(cls)):
        context_var = _DEPENDENCY_VARS_BY_TYPE[cls] = ContextVar(f"{cls.__name__}_dependency")
    return context_var


_DEPENDENCIES: set[type] = set()
_DEPENDENCY_VARS_BY_TYPE: WeakKeyDictionary[type, ContextVar] = WeakKeyDictionary()
_CONTEXT_PROVIDER_VARS_BY_TYPE: WeakKeyDictionary[type, ContextVar[UniformContextProvider]] = WeakKeyDictionary()
