from __future__ import annotations

from collections.abc import Mapping
from collections.abc import Sequence
from contextlib import AbstractAsyncContextManager
from contextlib import AbstractContextManager
from contextvars import ContextVar
from typing import Any
from typing import Callable
from typing import TypeVar
from typing import get_args
from typing import get_origin
from weakref import WeakKeyDictionary

from ninject._private.inspect import AsyncScopeParams
from ninject._private.inspect import ScopeParams
from ninject._private.inspect import SyncScopeParams
from ninject._private.inspect import get_scope_params
from ninject._private.inspect import required
from ninject._private.utils import async_exhaust_exits
from ninject._private.utils import exhaust_exits
from ninject.types import AsyncContextProvider
from ninject.types import AsyncValueProvider
from ninject.types import SyncContextProvider
from ninject.types import SyncValueProvider

R = TypeVar("R")

Unsetter = Callable[[], Any]
Setter = Callable[[], Unsetter]


def make_scope_setter(params: ScopeParams) -> Setter:
    if get_origin(params.provided_type) is tuple:
        partial_constructors = _make_partial_scope_constructors_for_tuple(params)
    else:
        partial_constructors = _make_partial_scope_constructor_for_scalar(params)

    def setter() -> Unsetter:
        new_scope_constructors = _SCOPE_CONSTRUCTOR_MAP_VAR.get()

        for cls, partial in partial_constructors.items():
            new_scope_constructors = {
                **new_scope_constructors,
                cls: lambda part=partial, old=new_scope_constructors: part(old),
            }

        reset_token = _SCOPE_CONSTRUCTOR_MAP_VAR.set(new_scope_constructors)

        return lambda: _SCOPE_CONSTRUCTOR_MAP_VAR.reset(reset_token)

    return setter


def get_scope_constructor(cls: type) -> ScopeConstructor:
    try:
        return _SCOPE_CONSTRUCTOR_MAP_VAR.get()[cls]
    except KeyError:
        msg = f"No provider declared for {cls}"
        raise RuntimeError(msg) from None


class Scope(AbstractContextManager[R], AbstractAsyncContextManager[R]):

    provider: Any
    provided_var: ContextVar

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.provided_var.name})"


ScopeConstructor = Callable[[], Scope]
ScopeConstructorMap = Mapping[type, ScopeConstructor]
PartialScopeConstructor = Callable[[ScopeConstructorMap], Scope]


class SyncScope(Scope[R]):
    def __init__(
        self,
        provider: SyncContextProvider[R],
        provided_var: ContextVar[R],
        required_scopes: Sequence[ScopeConstructor],
    ):
        self.reset_token = None
        self.provider = provider
        self.provided_var = provided_var
        self.required_scopes = [s() for s in required_scopes]

    def __enter__(self) -> R:
        try:
            return self.provided_var.get()
        except LookupError:
            for scope in self.required_scopes:
                scope.__enter__()
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
                    exhaust_exits(self.required_scopes)

    async def __aenter__(self) -> R:
        try:
            return self.provided_var.get()
        except LookupError:
            for scope in self.required_scopes:
                await scope.__aenter__()
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
                    await async_exhaust_exits(self.required_scopes)


class AsyncScope(Scope[R]):
    def __init__(
        self,
        context_provider: AsyncContextProvider[R],
        provided_var: ContextVar[R],
        required_scopes: Sequence[ScopeConstructor],
    ):
        self.reset_token = None
        self.provider = context_provider
        self.provided_var = provided_var
        self.required_scopes = [s() for s in required_scopes]

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
            for scope in self.required_scopes:
                await scope.__aenter__()
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
                    await async_exhaust_exits(self.required_scopes)


def _make_partial_scope_constructors_for_tuple(params: ScopeParams) -> Mapping[type, PartialScopeConstructor]:
    is_sync = isinstance(params, SyncScopeParams)

    tuple_type = params.provided_type
    tuple_item_types = get_args(tuple_type)

    _add_dependency_type(tuple_type)

    partial_constructors = dict(_make_partial_scope_constructor_for_scalar(params))

    for index, item_type in enumerate(tuple_item_types):
        item_function_provider = _make_item_provider(index, tuple_type, is_sync=is_sync)
        item_params = get_scope_params(item_function_provider, item_type, {"value": tuple_type})
        partial_constructors.update(_make_partial_scope_constructor_for_scalar(item_params))

    return partial_constructors


def _make_partial_scope_constructor_for_scalar(params: ScopeParams) -> Mapping[type, PartialScopeConstructor]:
    dependency_types = tuple(params.required_types.values())
    if isinstance(params, AsyncScopeParams):
        provider = params.provider
        provided_var = _get_dependency_var(params.provided_type)
        return {params.provided_type: lambda m: AsyncScope(provider, provided_var, [m[t] for t in dependency_types])}
    else:
        provider = params.provider
        provided_var = _get_dependency_var(params.provided_type)
        return {params.provided_type: lambda m: SyncScope(provider, provided_var, [m[t] for t in dependency_types])}


def _make_item_provider(item: int, value_type: type, *, is_sync: bool) -> SyncValueProvider | AsyncValueProvider:

    if is_sync:

        def sync_provide_item_field(*, value=required) -> Any:
            return value[item]

        sync_provide_item_field.__annotations__["value"] = value_type

        return sync_provide_item_field

    else:

        async def async_provide_item_field(*, value=required) -> Any:  # noqa: RUF029
            return value[item]

        async_provide_item_field.__annotations__["value"] = value_type

        return async_provide_item_field


def _add_dependency_type(anno: type) -> None:
    _VARS_BY_DEPENDENCY_TYPE[anno] = ContextVar(anno.__name__)


def _get_dependency_var(anno: type) -> ContextVar:
    return _VARS_BY_DEPENDENCY_TYPE.setdefault(anno, ContextVar(anno.__name__))


_SCOPE_CONSTRUCTOR_MAP_VAR = ContextVar[ScopeConstructorMap]("SCOPE_CONSTRUCTOR_MAP_VAR", default={})
_VARS_BY_DEPENDENCY_TYPE: WeakKeyDictionary[type, ContextVar] = WeakKeyDictionary()
