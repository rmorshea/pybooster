from __future__ import annotations

import sys
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from functools import wraps
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
    Sequence,
    TypeAlias,
    TypedDict,
    TypeVar,
    cast,
    get_args,
    get_origin,
    get_type_hints,
)
from weakref import WeakKeyDictionary

import ninject
from ninject.types import AsyncContextProvider, SyncContextProvider

P = ParamSpec("P")
R = TypeVar("R")


INJECTED = cast(Any, (type("INJECTED", (), {"__repr__": lambda _: "INJECTED"}))())


def add_dependency(cls: type) -> None:
    _DEPENDENCIES.add(cls)


def is_dependency(cls: type) -> bool:
    return cls in _DEPENDENCIES


def get_dependency_type_info(cls: type) -> tuple[Literal["attr", "item"] | None, dict[int | str, Any]]:
    if is_dependency(cls):
        return None, {}
    elif get_origin(cls) is tuple:
        return "item", {i: t for i, t in enumerate(get_args(cls)) if is_dependency(t)}
    else:
        return (
            "item" if issubclass(cls, dict) and TypedDict in getattr(cls, "__orig_bases__", []) else "attr",
            {k: t for k, t in get_type_hints(cls).items() if is_dependency(t)},
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


class SyncUniformContext(ContextManager[R], AsyncContextManager[R]):
    def __init__(
        self,
        var: ContextVar[R],
        context_provider: SyncContextProvider[R],
        dependencies: Sequence[type],
    ):
        self.var = var
        self.context_provider = context_provider
        self.token = None
        self.dependencies = dependencies
        self.dependency_contexts: list[UniformContext] = []

    def __enter__(self) -> R:
        try:
            return self.var.get()
        except LookupError:
            for cls in self.dependencies:
                (dependency_context := get_context_provider(cls)()).__enter__()
                self.dependency_contexts.append(dependency_context)
            self.context = context = self.context_provider()
            self.token = self.var.set(context.__enter__())
            return self.var.get()

    def __exit__(self, etype: Any, evalue: Any, atrace: Any, /) -> None:
        if self.token is not None:
            try:
                self.var.reset(self.token)
            finally:
                try:
                    self.context.__exit__(etype, evalue, atrace)
                finally:
                    exhaust_exits(self.dependency_contexts)

    async def __aenter__(self) -> R:
        try:
            return self.var.get()
        except LookupError:
            for var in self.dependencies:
                await (dependency_context := get_context_provider(var)()).__aenter__()
                self.dependency_contexts.append(dependency_context)
            self.context = context = self.context_provider()
            self.token = self.var.set(context.__enter__())
            return self.var.get()

    async def __aexit__(self, etype: Any, evalue: Any, atrace: Any, /) -> None:
        if self.token is not None:
            try:
                self.var.reset(self.token)
            finally:
                try:
                    self.context.__exit__(etype, evalue, atrace)
                finally:
                    await async_exhaust_exits(self.dependency_contexts)

    def __repr__(self) -> str:
        wrapped = _get_wrapped(self.context_provider)
        provider_str = getattr(wrapped, "__qualname__", str(wrapped))
        return f"{self.__class__.__name__}({self.var.name}, {provider_str})"


class AsyncUniformContext(ContextManager[R], AsyncContextManager[R]):
    def __init__(
        self,
        var: ContextVar[R],
        context_provider: AsyncContextProvider[R],
        dependencies: Sequence[type],
    ):
        self.var = var
        self.context_provider = context_provider
        self.token = None
        self.dependencies = dependencies
        self.dependency_contexts: list[UniformContext[Any]] = []

    def __enter__(self) -> R:
        try:
            return self.var.get()
        except LookupError:
            msg = f"Cannot use an async provider {self.var.name} in a sync context"
            raise RuntimeError(msg) from None

    def __exit__(self, etype: Any, evalue: Any, atrace: Any, /) -> None:
        pass

    async def __aenter__(self) -> R:
        try:
            return self.var.get()
        except LookupError:
            for cls in self.dependencies:
                await (dependency_context := get_context_provider(cls)()).__aenter__()
                self.dependency_contexts.append(dependency_context)
            self.context = context = self.context_provider()
            self.token = self.var.set(await context.__aenter__())
            return self.var.get()

    async def __aexit__(self, etype: Any, evalue: Any, atrace: Any, /) -> None:
        if self.token is not None:
            try:
                self.var.reset(self.token)
            finally:
                try:
                    await self.context.__aexit__(etype, evalue, atrace)
                finally:
                    await async_exhaust_exits(self.dependency_contexts)

    def __repr__(self) -> str:
        wrapped = _get_wrapped(self.context_provider)
        provider_str = getattr(wrapped, "__qualname__", str(wrapped))
        return f"{self.__class__.__name__}({self.var.name}, {provider_str})"


UniformContext: TypeAlias = "SyncUniformContext[R] | AsyncUniformContext[R]"
UniformContextProvider: TypeAlias = "Callable[[], UniformContext[R]]"


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


def asyncfunctioncontextmanager(func: Callable[[], Awaitable[R]]) -> AsyncContextProvider[R]:
    return wraps(func)(lambda: AsyncFunctionContextManager(func))


def syncfunctioncontextmanager(func: Callable[[], R]) -> SyncContextProvider[R]:
    return wraps(func)(lambda: SyncFunctionContextManager(func))


class AsyncFunctionContextManager(AsyncContextManager[R]):
    def __init__(self, func: Callable[[], Awaitable[R]]) -> None:
        self.func = func

    async def __aenter__(self) -> R:
        return await self.func()

    async def __aexit__(self, etype: Any, evalue: Any, atrace: Any, /) -> None:
        pass


class SyncFunctionContextManager(ContextManager[R]):
    def __init__(self, func: Callable[[], R]) -> None:
        self.func = func

    def __enter__(self) -> R:
        return self.func()

    def __exit__(self, etype: Any, evalue: Any, atrace: Any, /) -> None:
        pass


def exhaust_exits(ctxts: Sequence[ContextManager]) -> None:
    if not ctxts:
        return
    try:
        c, *ctxts = ctxts
        c.__exit__(*sys.exc_info())
    except Exception:
        exhaust_exits(ctxts)
        raise
    else:
        exhaust_exits(ctxts)


async def async_exhaust_exits(ctxts: Sequence[AsyncContextManager[Any]]) -> None:
    if not ctxts:
        return
    try:
        c, *ctxts = ctxts
        await c.__aexit__(*sys.exc_info())
    except Exception:
        await async_exhaust_exits(ctxts)
        raise
    else:
        await async_exhaust_exits(ctxts)


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


_DEPENDENCY_VARS_BY_TYPE: WeakKeyDictionary[type, ContextVar] = WeakKeyDictionary()
_CONTEXT_PROVIDER_VARS_BY_TYPE: WeakKeyDictionary[type, ContextVar[UniformContextProvider]] = WeakKeyDictionary()


_DEPENDENCIES: set[type] = set()
