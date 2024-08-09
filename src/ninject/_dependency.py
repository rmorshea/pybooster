from __future__ import annotations

from collections.abc import Sequence
from contextlib import AbstractAsyncContextManager, AbstractContextManager
from contextvars import ContextVar
from types import UnionType
from typing import Any, Callable, TypeAlias, TypeVar, get_args, get_origin

from ninject._inspect import get_wrapped, unwrap_annotated
from ninject._utils import async_exhaust_exits, exhaust_exits
from ninject.types import AsyncContextProvider, SyncContextProvider

R = TypeVar("R")


def get_dependency_type(anno: type) -> type | None:
    anno = unwrap_annotated(anno)
    if get_origin(anno) is UnionType:
        deps = [get_dependency_type(arg) for arg in get_args(anno)]
        if len(deps) == 1:
            return deps[0]
        elif len(deps) == 0:
            return None
        else:
            msg = f"Union {anno} has more than one dependency: {deps}"
            raise ValueError(msg)
    elif is_dependency_type(anno):
        return anno
    else:
        return None


def get_dependency_name(anno: type) -> str:
    return get_dependency_value_var(anno).name


def is_dependency_type(anno: type) -> bool:
    return anno in _DEPENDENCY_VALUE_VARS_BY_DEPENDENCY_TYPE


def add_dependency_type(name: str, anno: type) -> None:
    _DEPENDENCY_VALUE_VARS_BY_DEPENDENCY_TYPE[anno] = ContextVar(name)


def setdefault_dependency_value_var(anno: type) -> ContextVar:
    return _DEPENDENCY_VALUE_VARS_BY_DEPENDENCY_TYPE.setdefault(anno, ContextVar(anno.__name__))


def get_dependency_value_var(anno: type) -> ContextVar:
    try:
        return _DEPENDENCY_VALUE_VARS_BY_DEPENDENCY_TYPE[anno]
    except KeyError:
        msg = f"{anno} was not declared as a dependency"
        raise ValueError(msg) from None


DependencyContextProvider: TypeAlias = "Callable[[], DependencyContext[R]]"


def set_dependency_context_provider(cls: type[R], provider: DependencyContextProvider[R]) -> Callable[[], None]:
    if not (var := _DEPENDENCY_CONTEXT_PROVIDER_VARS_BY_DEPENDENCY_TYPE.get(cls)):
        var = _DEPENDENCY_CONTEXT_PROVIDER_VARS_BY_DEPENDENCY_TYPE[cls] = ContextVar(f"Provider:{cls.__name__}")
    token = var.set(provider)
    return lambda: var.reset(token)


def get_dependency_context_provider(cls: type[R]) -> DependencyContextProvider[R]:
    try:
        var = _DEPENDENCY_CONTEXT_PROVIDER_VARS_BY_DEPENDENCY_TYPE[cls]
    except KeyError:
        msg = f"No provider declared for {cls}"
        raise RuntimeError(msg) from None
    try:
        return var.get()
    except LookupError:
        msg = f"No active provider for {cls}"
        raise RuntimeError(msg) from None


class DependencyContext(AbstractContextManager[R], AbstractAsyncContextManager[R]):

    provider: Any
    provided_var: ContextVar

    def __repr__(self) -> str:
        wrapped = get_wrapped(self.provider)
        provider_str = getattr(wrapped, "__qualname__", str(wrapped))
        return f"{self.__class__.__name__}({self.provided_var.name}, {provider_str})"


class SyncDependencyContext(DependencyContext[R]):
    def __init__(
        self,
        provider: SyncContextProvider[R],
        provided_var: ContextVar[R],
        required_types: Sequence[type],
    ):
        self.reset_token = None
        self.provider = provider
        self.provided_var = provided_var
        self.required_types = required_types
        self.required_contexts: list[DependencyContext] = []

    def __enter__(self) -> R:
        try:
            return self.provided_var.get()
        except LookupError:
            for dep_type in self.required_types:
                (dependency_context := get_dependency_context_provider(dep_type)()).__enter__()
                self.required_contexts.append(dependency_context)
            self.context = context = self.provider()
            self.reset_token = self.provided_var.set(context.__enter__())
            return self.provided_var.get()

    def __exit__(self, etype: Any, evalue: Any, atrace: Any, /) -> None:
        if self.reset_token is not None:
            try:
                self.provided_var.reset(self.reset_token)
            finally:
                try:
                    self.context.__exit__(etype, evalue, atrace)
                finally:
                    exhaust_exits(self.required_contexts)

    async def __aenter__(self) -> R:
        try:
            return self.provided_var.get()
        except LookupError:
            for req_type in self.required_types:
                await (dependency_context := get_dependency_context_provider(req_type)()).__aenter__()
                self.required_contexts.append(dependency_context)
            self.context = context = self.provider()
            self.reset_token = self.provided_var.set(context.__enter__())
            return self.provided_var.get()

    async def __aexit__(self, etype: Any, evalue: Any, atrace: Any, /) -> None:
        if self.reset_token is not None:
            try:
                self.provided_var.reset(self.reset_token)
            finally:
                try:
                    self.context.__exit__(etype, evalue, atrace)
                finally:
                    await async_exhaust_exits(self.required_contexts)


class AsyncDependencyContext(DependencyContext[R]):
    def __init__(
        self,
        context_provider: AsyncContextProvider[R],
        provided_var: ContextVar[R],
        required_types: Sequence[type],
    ):
        self.reset_token = None
        self.provider = context_provider
        self.provided_var = provided_var
        self.required_types = required_types
        self.required_contexts: list[DependencyContext[Any]] = []

    def __enter__(self) -> R:
        try:
            return self.provided_var.get()
        except LookupError:
            msg = f"Cannot use an async provider {self.provided_var.name} in a sync context"
            raise RuntimeError(msg) from None

    def __exit__(self, etype: Any, evalue: Any, atrace: Any, /) -> None:
        pass

    async def __aenter__(self) -> R:
        try:
            return self.provided_var.get()
        except LookupError:
            for req_type in self.required_types:
                await (dependency_context := get_dependency_context_provider(req_type)()).__aenter__()
                self.required_contexts.append(dependency_context)
            self.context = context = self.provider()
            self.reset_token = self.provided_var.set(await context.__aenter__())
            return self.provided_var.get()

    async def __aexit__(self, etype: Any, evalue: Any, atrace: Any, /) -> None:
        if self.reset_token is not None:
            try:
                self.provided_var.reset(self.reset_token)
            finally:
                try:
                    await self.context.__aexit__(etype, evalue, atrace)
                finally:
                    await async_exhaust_exits(self.required_contexts)


_DEPENDENCY_CONTEXT_PROVIDER_VARS_BY_DEPENDENCY_TYPE: dict[type, ContextVar[DependencyContextProvider]] = {}
_DEPENDENCY_VALUE_VARS_BY_DEPENDENCY_TYPE: dict[type, ContextVar] = {}
