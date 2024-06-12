from __future__ import annotations

import inspect
import sys
from contextvars import ContextVar
from typing import (
    Annotated,
    Any,
    AsyncContextManager,
    Awaitable,
    Callable,
    ContextManager,
    Mapping,
    ParamSpec,
    Sequence,
    TypeAlias,
    TypeVar,
    cast,
    get_args,
    get_origin,
)

from ninject.types import (
    AsyncContextProvider,
    AsyncFunctionProvider,
    SyncContextProvider,
    SyncFunctionProvider,
)

P = ParamSpec("P")
R = TypeVar("R")


INJECTED = cast(Any, (type("INJECTED", (), {"__repr__": lambda _: "INJECTED"}))())


def get_wrapped(func: Callable[P, R]) -> Callable[P, R]:
    while maybe_func := getattr(func, "__wrapped__", None):
        func = maybe_func
    return func


def get_injected_context_vars_from_callable(func: Callable[..., Any]) -> Mapping[str, ContextVar]:
    context_vars: dict[str, ContextVar] = {}

    for param in inspect.signature(func).parameters.values():
        if param.default is INJECTED:
            if param.kind is not inspect.Parameter.KEYWORD_ONLY:
                msg = f"Expected injected parameter {param.name!r} to be keyword-only"
                raise TypeError(msg)
            anno = param.annotation
            if isinstance(anno, str):
                try:
                    anno = eval(anno, func.__globals__, func.__closure__)  # noqa: S307
                except NameError as e:
                    msg = f"{e} - is it defined as a global?"
                    raise NameError(msg) from None
            if get_origin(anno) is not Annotated:
                msg = (
                    f"Expected {param.name!r} to be annotated with a "
                    f"ContextVar - did use Dependency[{anno}, 'name']?"
                )
                raise TypeError(msg)
            if var := get_context_var_from_annotation(anno):
                context_vars[param.name] = var
            else:
                msg = (
                    f"Expected {param.name!r} to be annotated with a "
                    f"ContextVar - did use Dependency[{anno}, 'name']?"
                )
                raise TypeError(msg)

    return context_vars


def get_context_var_from_annotation(anno: Any) -> ContextVar | None:
    if get_origin(anno) is not Annotated:
        return None
    _, *metadata = get_args(anno)
    var: ContextVar | None = None
    for meta in metadata:
        if isinstance(meta, ContextVar):
            if var is not None:
                msg = "Expected exactly one ContextVar"
                raise TypeError(msg)
            var = meta
    return var


class SyncUniformContext(ContextManager[R], AsyncContextManager[R]):
    def __init__(
        self,
        var: ContextVar[R],
        context_provider: SyncContextProvider[R],
        dependencies: Sequence[ContextVar],
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
            for var in self.dependencies:
                (dependency_context := get_context_provider(var)()).__enter__()
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


class AsyncUniformContext(ContextManager[R], AsyncContextManager[R]):
    def __init__(
        self,
        var: ContextVar[R],
        context_provider: AsyncContextProvider[R],
        dependencies: Sequence[ContextVar],
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
            msg = "Cannot use an async context manager in a sync context"
            raise RuntimeError(msg) from None

    def __exit__(self, etype: Any, evalue: Any, atrace: Any, /) -> None:
        pass

    async def __aenter__(self) -> R:
        try:
            return self.var.get()
        except LookupError:
            for var in self.dependencies:
                await (dependency_context := get_context_provider(var)()).__aenter__()
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


UniformContext: TypeAlias = "SyncUniformContext[R] | AsyncUniformContext[R]"
UniformContextProvider: TypeAlias = "Callable[[], UniformContext[R]]"


def asyncfunctioncontextmanager(func: Callable[[], Awaitable[R]]) -> AsyncFunctionProvider[R]:
    return lambda: AsyncFunctionContextManager(func)


def syncfunctioncontextmanager(func: Callable[[], R]) -> SyncFunctionProvider[R]:
    return lambda: SyncFunctionContextManager(func)


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


def set_context_provider(
    dependency_var: ContextVar[R],
    provider: UniformContextProvider[R],
) -> Callable[[], None]:
    if not (context_provider_var := _CONTEXT_PROVIDER_VARS_BY_DEPENDENCY_VAR.get(dependency_var)):
        context_provider_var = _CONTEXT_PROVIDER_VARS_BY_DEPENDENCY_VAR[dependency_var] = ContextVar(
            f"{dependency_var.name}_context_provider"
        )
    token = context_provider_var.set(provider)
    return lambda: context_provider_var.reset(token)


def get_context_provider(dependency_var: ContextVar[R]) -> UniformContextProvider[R]:
    try:
        context_provider_var = _CONTEXT_PROVIDER_VARS_BY_DEPENDENCY_VAR[dependency_var]
    except KeyError:
        msg = f"No provider declared for {dependency_var}"
        raise RuntimeError(msg) from None
    return context_provider_var.get()


UniformContext: TypeAlias = "SyncUniformContext[R] | AsyncUniformContext[R]"
UniformContextProvider: TypeAlias = "Callable[[], UniformContext[R]]"


_CONTEXT_PROVIDER_VARS_BY_DEPENDENCY_VAR: dict[ContextVar, ContextVar[UniformContextProvider]] = {}
