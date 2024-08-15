from __future__ import annotations

from asyncio import iscoroutinefunction
from collections.abc import AsyncGenerator
from collections.abc import AsyncIterator
from collections.abc import Generator
from collections.abc import Iterator
from collections.abc import Mapping
from contextlib import AbstractAsyncContextManager
from contextlib import AbstractContextManager
from contextlib import asynccontextmanager
from contextlib import contextmanager
from dataclasses import dataclass
from inspect import Parameter
from inspect import isasyncgenfunction
from inspect import isfunction
from inspect import isgeneratorfunction
from inspect import signature
from typing import Annotated
from typing import Any
from typing import Callable
from typing import Generic
from typing import ParamSpec
from typing import TypeVar
from typing import cast
from typing import get_args
from typing import get_origin
from typing import get_type_hints

import ninject
from ninject._private.utils import asyncfunctioncontextmanager
from ninject._private.utils import sentinel
from ninject._private.utils import syncfunctioncontextmanager
from ninject.types import AsyncContextProvider
from ninject.types import SyncContextProvider

P = ParamSpec("P")
R = TypeVar("R")


required = sentinel("REQUIRED")
"""Declare that an injected parameter is required."""


class Default(Generic[R]):

    def __init__(self, value: R) -> None:
        self.value = value

    def __getitem__(self, value: R) -> R:
        return cast(R, Default(value))

    def __call__(self, value: R) -> R:
        return cast(R, Default(value))

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, Default) and self.value == other.value

    def __hash__(self) -> int:
        return hash(self.value)

    def __repr__(self) -> str:
        return f"DEFAULT({self.value!r})"


default = object.__new__(Default)
"""Declare a default value for an injected parameter."""


def get_dependency_types_from_callable(func: Callable[..., Any]) -> Mapping[str, type]:
    dependency_types: dict[str, type] = {}

    for param in signature(get_wrapped(func)).parameters.values():
        if param.default is required or isinstance(param.default, Default):
            if param.kind is not Parameter.KEYWORD_ONLY:
                msg = f"Expected injected parameter {param.name!r} to be keyword-only"
                raise TypeError(msg)
            anno = param.annotation
            if isinstance(anno, str):
                try:
                    anno = eval(anno, func.__globals__)  # noqa: S307
                except NameError as e:
                    msg = f"{e} - is it defined as a global?"
                    raise NameError(msg) from None
            dependency_types[param.name] = anno

    return dependency_types


def get_dependency_defaults_from_callable(func: Callable[..., Any]) -> Mapping[str, Any]:
    dependency_defaults: dict[str, Any] = {}

    for param in signature(get_wrapped(func)).parameters.values():
        if isinstance(param.default, Default):
            dependency_defaults[param.name] = param.default.value

    return dependency_defaults


def unwrap_annotated(anno: type) -> type:
    return get_args(anno)[0] if get_origin(anno) is Annotated else anno


def get_wrapped(func: Callable[P, R]) -> Callable[P, R]:
    while maybe_func := getattr(func, "__wrapped__", None):
        func = maybe_func
    return func


@dataclass(kw_only=True)
class SyncScopeParams(Generic[R]):
    provided_type: type[R]
    required_types: Mapping[str, type]
    provider: SyncContextProvider[R]


@dataclass(kw_only=True)
class AsyncScopeParams(Generic[R]):
    provided_type: type[R]
    required_types: Mapping[str, type]
    provider: AsyncContextProvider[R]


ScopeParams = SyncScopeParams[R] | AsyncScopeParams[R]


def get_scope_params(
    provider: Callable,
    provides_type: Any | None = None,
    required_types: Mapping[str, type] | None = None,
) -> ScopeParams:
    required_types = required_types or get_dependency_types_from_callable(provider)
    if provides_type is None:
        return _infer_scope_params(provider, required_types)
    else:
        return _get_scope_params(provider, provides_type, required_types)


def _get_scope_params(provider: Callable, provides_type: Any, required_types: Mapping[str, type]) -> ScopeParams:
    if isinstance(provider, type):
        if issubclass(provider, AbstractContextManager):
            return SyncScopeParams(
                provided_type=provides_type,
                provider=provider,
                required_types=required_types,
            )
        elif issubclass(provider, AbstractAsyncContextManager):
            return AsyncScopeParams(
                provided_type=provides_type,
                provider=provider,
                required_types=required_types,
            )
    elif iscoroutinefunction(provider):
        return AsyncScopeParams(
            provided_type=provides_type,
            provider=asyncfunctioncontextmanager(ninject.inject(provider)),
            required_types=required_types,
        )
    elif isasyncgenfunction(provider):
        return AsyncScopeParams(
            provided_type=provides_type,
            provider=asynccontextmanager(ninject.inject(provider)),
            required_types=required_types,
        )
    elif isgeneratorfunction(provider):
        return SyncScopeParams(
            provided_type=provides_type,
            provider=contextmanager(ninject.inject(provider)),
            required_types=required_types,
        )
    elif isfunction(provider):
        return SyncScopeParams(
            provided_type=provides_type,
            provider=syncfunctioncontextmanager(ninject.inject(provider)),
            required_types=required_types,
        )
    msg = f"Unsupported provider type {provides_type!r} - expected a callable or context manager."
    raise TypeError(msg)


def _infer_scope_params(provider: Any, required_types: Mapping[str, type]) -> ScopeParams:
    if isinstance(provider, type):
        if issubclass(provider, (AbstractContextManager, AbstractAsyncContextManager)):
            return _get_scope_params(provider, _get_context_manager_type(provider), required_types)
        else:
            msg = f"Unsupported provider type {provider!r}  - expected a callable or context manager."
            raise TypeError(msg)

    try:
        type_hints = get_type_hints(provider)
    except TypeError as error:  # nocov
        msg = f"Unsupported provider type {provider!r}  - expected a callable or context manager."
        raise TypeError(msg) from error

    try:
        return_type = type_hints["return"]
    except KeyError:
        msg = f"Cannot determine return type of {provider!r} - no return type annotation."
        raise TypeError(msg) from None

    return_type = unwrap_annotated(return_type)
    return_type_origin = get_origin(return_type)

    if return_type_origin is None:
        return _get_scope_params(provider, return_type, required_types)
    elif issubclass(return_type_origin, (AsyncIterator, AsyncGenerator, Iterator, Generator)):
        return _get_scope_params(provider, get_args(return_type)[0], required_types)
    else:
        return _get_scope_params(provider, return_type, required_types)


def _get_context_manager_type(cls: type[AbstractContextManager | AbstractAsyncContextManager]) -> Any:
    method_name = "__aenter__" if issubclass(cls, AbstractAsyncContextManager) else "__enter__"
    provides_type = get_scope_params(getattr(cls, method_name)).provided_type
    return provides_type
