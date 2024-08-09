from __future__ import annotations

from asyncio import iscoroutinefunction
from collections.abc import AsyncGenerator, AsyncIterator, Generator, Iterator, Mapping
from contextlib import AbstractAsyncContextManager, AbstractContextManager, asynccontextmanager, contextmanager
from dataclasses import dataclass
from inspect import Parameter, currentframe, isasyncgenfunction, isfunction, isgeneratorfunction, signature
from typing import Annotated, Any, Callable, Generic, ParamSpec, TypeVar, cast, get_args, get_origin, get_type_hints

import ninject
from ninject._utils import asyncfunctioncontextmanager, syncfunctioncontextmanager
from ninject.types import AsyncContextProvider, SyncContextProvider

P = ParamSpec("P")
R = TypeVar("R")


INJECTED = cast(Any, type("Injected", (), {"__repr__": lambda _: "INJECTED"})())


def get_injected_dependency_types_from_callable(func: Callable[..., Any]) -> Mapping[str, type]:
    dependency_types: dict[str, type] = {}

    for param in signature(get_wrapped(func)).parameters.values():
        if param.default is INJECTED:
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


def get_caller_module_name(depth: int = 1) -> str | None:
    frame = currentframe()
    for _ in range(depth + 1):
        if frame is None:
            return None  # nocov
        frame = frame.f_back
    if frame is None:
        return None  # nocov
    return frame.f_globals.get("__name__")


def unwrap_annotated(anno: type) -> type:
    return get_args(anno)[0] if get_origin(anno) is Annotated else anno


def get_wrapped(func: Callable[P, R]) -> Callable[P, R]:
    while maybe_func := getattr(func, "__wrapped__", None):
        func = maybe_func
    return func


@dataclass(kw_only=True)
class SyncProviderInfo(Generic[R]):
    provided_type: type[R]
    provider: SyncContextProvider[R]


@dataclass(kw_only=True)
class AsyncProviderInfo(Generic[R]):
    provided_type: type[R]
    provider: AsyncContextProvider[R]


ProviderInfo = SyncProviderInfo[R] | AsyncProviderInfo[R]


def get_provider_info(provider: Callable, provides_type: Any | None = None) -> ProviderInfo:
    if provides_type is None:
        return _infer_provider_info(provider)
    else:
        return _get_provider_info(provider, provides_type)


def _get_provider_info(provider: Callable, provides_type: Any) -> ProviderInfo:
    if isinstance(provider, type):
        if issubclass(provider, AbstractContextManager):
            return SyncProviderInfo(provided_type=provides_type, provider=provider)
        elif issubclass(provider, AbstractAsyncContextManager):
            return AsyncProviderInfo(provided_type=provides_type, provider=provider)
    elif iscoroutinefunction(provider):
        return AsyncProviderInfo(
            provided_type=provides_type,
            provider=asyncfunctioncontextmanager(ninject.inject(provider)),
        )
    elif isasyncgenfunction(provider):
        return AsyncProviderInfo(
            provided_type=provides_type,
            provider=asynccontextmanager(ninject.inject(provider)),
        )
    elif isgeneratorfunction(provider):
        return SyncProviderInfo(
            provided_type=provides_type,
            provider=contextmanager(ninject.inject(provider)),
        )
    elif isfunction(provider):
        return SyncProviderInfo(
            provided_type=provides_type,
            provider=syncfunctioncontextmanager(ninject.inject(provider)),
        )
    msg = f"Unsupported provider type {provides_type!r} - expected a callable or context manager."
    raise TypeError(msg)


def _infer_provider_info(provider: Any) -> ProviderInfo:
    if isinstance(provider, type):
        if issubclass(provider, (AbstractContextManager, AbstractAsyncContextManager)):
            return _get_provider_info(provider, _get_context_manager_type(provider))
        else:
            msg = f"Unsupported provider type {provider!r}  - expected a callable or context manager."
            raise TypeError(msg)

    try:
        type_hints = get_type_hints(provider)
    except TypeError as error:  # nocov
        msg = f"Unsupported provider type {provider!r}  - expected a callable or context manager."
        raise TypeError(msg) from error

    return_type = unwrap_annotated(type_hints.get("return"))
    return_type_origin = get_origin(return_type)

    if return_type is None:
        msg = f"Cannot determine return type of {provider!r}"
        raise TypeError(msg)

    if return_type_origin is None:
        return _get_provider_info(provider, return_type)
    elif issubclass(return_type_origin, (AsyncIterator, AsyncGenerator, Iterator, Generator)):
        return _get_provider_info(provider, get_args(return_type)[0])
    else:
        return _get_provider_info(provider, return_type)


def _get_context_manager_type(cls: type[AbstractContextManager | AbstractAsyncContextManager]) -> Any:
    method_name = "__aenter__" if issubclass(cls, AbstractAsyncContextManager) else "__enter__"
    provides_type = get_provider_info(getattr(cls, method_name)).provided_type
    return provides_type
