from __future__ import annotations

import sys
from contextvars import ContextVar
from functools import wraps
from typing import (
    Any,
    AsyncContextManager,
    Awaitable,
    Callable,
    ContextManager,
    ParamSpec,
    Sequence,
    TypeAlias,
    TypeVar,
)

from ninject._private._global import get_context_provider
from ninject._private._inspect import _get_wrapped
from ninject.types import AsyncContextProvider, SyncContextProvider

P = ParamSpec("P")
R = TypeVar("R")


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
