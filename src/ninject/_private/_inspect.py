from __future__ import annotations

from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass, field
from inspect import Parameter, isasyncgenfunction, iscoroutinefunction, isfunction, isgeneratorfunction, signature
from typing import (
    Annotated,
    Any,
    AsyncContextManager,
    AsyncGenerator,
    AsyncIterator,
    Awaitable,
    Callable,
    ContextManager,
    Coroutine,
    Generator,
    Generic,
    Iterator,
    Literal,
    Mapping,
    ParamSpec,
    TypedDict,
    TypeVar,
    cast,
    get_args,
    get_origin,
    get_type_hints,
)

import ninject
from ninject._private._contexts import (
    AsyncUniformContext,
    SyncUniformContext,
    asyncfunctioncontextmanager,
    syncfunctioncontextmanager,
)
from ninject._private._global import has_dependency
from ninject.types import AsyncContextProvider, SyncContextProvider

P = ParamSpec("P")
R = TypeVar("R")


INJECTED = cast(Any, (type("INJECTED", (), {"__repr__": lambda _: "INJECTED"}))())


def get_dependency_type_info(cls: type) -> tuple[Literal["attr", "item"] | None, dict[int | str, Any]]:
    if has_dependency(cls):
        return None, {}
    elif get_origin(cls) is tuple:
        return "item", {i: t for i, t in enumerate(get_args(cls)) if has_dependency(t)}
    else:
        return (
            "item" if issubclass(cls, dict) and TypedDict in getattr(cls, "__orig_bases__", []) else "attr",
            {k: t for k, t in get_type_hints(cls).items() if has_dependency(t)},
        )


def get_provider_info(provider: Callable, provides_type: Any | None = None) -> ProviderInfo:
    if provides_type is None:
        return _infer_provider_info(provider)
    else:
        return _get_provider_info(provider, provides_type)


def get_injected_dependency_types_from_callable(func: Callable[..., Any]) -> Mapping[str, type]:
    dependency_types: dict[str, type] = {}

    for param in signature(_get_wrapped(func)).parameters.values():
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


@dataclass(kw_only=True)
class SyncProviderInfo(Generic[R]):
    sync: Literal[True] = field(default=True, init=False)
    uniform_context_type: type[SyncUniformContext[R]] = field(default=SyncUniformContext, init=False)
    provides_type: type[R]
    context_provider: SyncContextProvider[R]


@dataclass(kw_only=True)
class AsyncProviderInfo(Generic[R]):
    sync: Literal[False] = field(default=False, init=False)
    uniform_context_type: type[AsyncUniformContext[R]] = field(default=AsyncUniformContext, init=False)
    provides_type: type[R]
    context_provider: AsyncContextProvider[R]


ProviderInfo = SyncProviderInfo[R] | AsyncProviderInfo[R]


def _get_wrapped(func: Callable[P, R]) -> Callable[P, R]:
    while maybe_func := getattr(func, "__wrapped__", None):
        func = maybe_func
    return func


def _get_context_manager_type(cls: type[ContextManager | AsyncContextManager]) -> Any:
    method_name = "__aenter__" if issubclass(cls, AsyncContextManager) else "__enter__"
    for base in getattr(cls, "__orig_bases__", ()):
        if (
            (base_origin := get_origin(base))
            and issubclass(base_origin, ContextManager)
            and (base_args := get_args(base))
        ):
            provides_type = base_args[0]
            break
    else:
        provides_type = get_provider_info(getattr(cls, method_name)).provides_type
    return provides_type


def _get_provider_info(provider: Callable, provides_type: Any) -> ProviderInfo:
    if isinstance(provider, type):
        if issubclass(provider, ContextManager):
            return SyncProviderInfo(provides_type=provides_type, context_provider=provider)
        elif issubclass(provider, AsyncContextManager):
            return AsyncProviderInfo(provides_type=provides_type, context_provider=provider)
        else:
            msg = f"Unsupported provider type: {provider!r}"
            raise TypeError(msg)
    elif iscoroutinefunction(provider):
        return AsyncProviderInfo(
            provides_type=provides_type,
            context_provider=asyncfunctioncontextmanager(ninject.inject(provider)),
        )
    elif isasyncgenfunction(provider):
        return AsyncProviderInfo(
            provides_type=provides_type,
            context_provider=asynccontextmanager(ninject.inject(provider)),
        )
    elif isgeneratorfunction(provider):
        return SyncProviderInfo(
            provides_type=provides_type,
            context_provider=contextmanager(ninject.inject(provider)),
        )
    elif isfunction(provider):
        return SyncProviderInfo(
            provides_type=provides_type,
            context_provider=syncfunctioncontextmanager(ninject.inject(provider)),
        )
    else:
        msg = f"Unsupported provider type: {provider!r}"
        raise TypeError(msg)


def _infer_provider_info(provider: Any) -> ProviderInfo:
    if isinstance(provider, type):
        if issubclass(provider, ContextManager):
            return SyncProviderInfo(
                provides_type=_get_context_manager_type(provider),
                context_provider=provider,
            )
        elif issubclass(provider, AsyncContextManager):
            return AsyncProviderInfo(
                provides_type=_get_context_manager_type(provider),
                context_provider=provider,
            )
        else:
            msg = f"Unsupported provider type: {provider!r}"
            raise TypeError(msg)

    try:
        type_hints = get_type_hints(provider)
    except TypeError:
        msg = f"Expected a function or class, got {provider!r}"
        raise TypeError(msg) from None

    return_type = _unwrap_annotated(type_hints.get("return"))
    return_type_origin = get_origin(return_type)

    if return_type is None:
        msg = f"Cannot determine return type of {provider!r}"
        raise TypeError(msg)

    if return_type_origin is None:
        if iscoroutinefunction(provider):
            return AsyncProviderInfo(
                provides_type=return_type,
                context_provider=asyncfunctioncontextmanager(ninject.inject(provider)),
            )
        else:
            return SyncProviderInfo(
                provides_type=return_type,
                context_provider=syncfunctioncontextmanager(ninject.inject(provider)),
            )
    elif issubclass(return_type_origin, (AsyncIterator, AsyncGenerator)):
        return AsyncProviderInfo(
            provides_type=get_args(return_type)[0],
            context_provider=asynccontextmanager(ninject.inject(provider)),
        )
    elif issubclass(return_type_origin, (Iterator, Generator)):
        return SyncProviderInfo(
            provides_type=get_args(return_type)[0],
            context_provider=contextmanager(ninject.inject(provider)),
        )
    elif issubclass(return_type_origin, Awaitable):
        return AsyncProviderInfo(
            provides_type=get_args(return_type)[0],
            context_provider=asyncfunctioncontextmanager(ninject.inject(provider)),
        )
    elif issubclass(return_type_origin, Coroutine):
        coro_yield_type, _, cor_return_type = get_args(return_type)
        if _unwrap_annotated(coro_yield_type) in (None, Any):
            return AsyncProviderInfo(
                provides_type=get_args(return_type)[0],
                context_provider=asynccontextmanager(ninject.inject(provider)),
            )
        else:
            return AsyncProviderInfo(
                provides_type=cor_return_type,
                context_provider=asyncfunctioncontextmanager(ninject.inject(provider)),
            )
    elif issubclass(return_type_origin, ContextManager):
        return SyncProviderInfo(
            provides_type=get_provider_info(return_type).provides_type,
            context_provider=syncfunctioncontextmanager(ninject.inject(provider)),
        )
    elif issubclass(return_type_origin, AsyncContextManager):
        return AsyncProviderInfo(
            provides_type=get_provider_info(return_type).provides_type,
            context_provider=asyncfunctioncontextmanager(ninject.inject(provider)),
        )
    elif isfunction(provider):
        return SyncProviderInfo(
            provides_type=return_type,
            context_provider=syncfunctioncontextmanager(ninject.inject(provider)),
        )
    else:
        msg = f"Unsupported provider type: {provider!r}"
        raise TypeError(msg)


def _unwrap_annotated(anno: Any) -> Any:
    if get_origin(anno) is Annotated:
        return get_args(anno)[0]
    return anno
