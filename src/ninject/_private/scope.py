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

from ninject._private.inspect import INJECTED
from ninject._private.inspect import AsyncScopeParams
from ninject._private.inspect import ScopeParams
from ninject._private.inspect import SyncScopeParams
from ninject._private.inspect import get_dependency_types_from_callable
from ninject._private.inspect import get_scope_params
from ninject._private.utils import async_exhaust_exits
from ninject._private.utils import exhaust_exits
from ninject.types import AsyncContextProvider
from ninject.types import AsyncValueProvider
from ninject.types import SyncContextProvider
from ninject.types import SyncValueProvider

R = TypeVar("R")


def make_scope_providers(
    params: ScopeParams, required_parameters: Mapping[str, type] | None
) -> Mapping[type, ScopeProvider]:
    if get_origin(params.provided_type) is tuple:
        return _make_scope_providers_for_tuple(params, required_parameters)
    else:
        return {params.provided_type: _make_scope_providers_for_scalar(params, required_parameters)}


def set_scope_provider(cls: type[R], provider: ScopeProvider[R]) -> Callable[[], None]:
    if not (var := _SCOPE_PROVIDER_VARS_BY_DEPENDENCY_TYPE.get(cls)):
        var = _SCOPE_PROVIDER_VARS_BY_DEPENDENCY_TYPE[cls] = ContextVar(f"Provider:{cls.__name__}")
    token = var.set(provider)
    return lambda: var.reset(token)


def get_scope_provider(cls: type[R]) -> ScopeProvider[R]:
    try:
        var = _SCOPE_PROVIDER_VARS_BY_DEPENDENCY_TYPE[cls]
    except KeyError:
        msg = f"No provider declared for {cls}"
        raise RuntimeError(msg) from None
    try:
        return var.get()
    except LookupError:  # nocov
        msg = f"No active provider for {cls}"
        raise RuntimeError(msg) from None


class Scope(AbstractContextManager[R], AbstractAsyncContextManager[R]):

    provider: Any
    provided_var: ContextVar


ScopeProvider = Callable[[], Scope[R]]


class SyncScope(Scope[R]):
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
        self.required_contexts: list[Scope] = []

    def __enter__(self) -> R:
        try:
            return self.provided_var.get()
        except LookupError:
            for dep_type in self.required_types:
                (dependency_context := get_scope_provider(dep_type)()).__enter__()
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
                await (dependency_context := get_scope_provider(req_type)()).__aenter__()
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


class AsyncScope(Scope[R]):
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
        self.required_contexts: list[Scope[Any]] = []

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
                await (dependency_context := get_scope_provider(req_type)()).__aenter__()
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


def _make_scope_providers_for_tuple(
    params: ScopeParams,
    required_parameter_types: Mapping[str, type] | None,
) -> dict[type, ScopeProvider]:
    is_sync = isinstance(params, SyncScopeParams)

    tuple_type = params.provided_type
    tuple_item_types = get_args(tuple_type)

    _add_dependency_type(tuple_type)

    providers = {tuple_type: _make_scope_providers_for_scalar(params, required_parameter_types)}

    for index, item_type in enumerate(tuple_item_types):
        item_dependencies = {"value": tuple_type}
        item_function_provider = _make_item_provider(index, tuple_type, is_sync=is_sync)
        item_params = get_scope_params(item_function_provider, provides_type=item_type)
        providers[item_type] = _make_scope_providers_for_scalar(item_params, required_parameter_types=item_dependencies)

    return providers


def _make_scope_providers_for_scalar(
    params: ScopeParams,
    required_parameter_types: Mapping[str, type] | None,
) -> ScopeProvider:
    if required_parameter_types is None:
        required_parameter_types = get_dependency_types_from_callable(params.provider)

    dependency_types = tuple(required_parameter_types.values())
    if isinstance(params, AsyncScopeParams):
        provider = params.provider
        provided_var = _get_dependency_var(params.provided_type)
        return lambda: AsyncScope(provider, provided_var, dependency_types)
    else:
        provider = params.provider
        provided_var = _get_dependency_var(params.provided_type)
        return lambda: SyncScope(provider, provided_var, dependency_types)


def _make_item_provider(item: int, value_type: type, *, is_sync: bool) -> SyncValueProvider | AsyncValueProvider:

    if is_sync:

        def sync_provide_item_field(*, value=INJECTED) -> Any:
            return value[item]

        sync_provide_item_field.__annotations__["value"] = value_type

        return sync_provide_item_field

    else:

        async def async_provide_item_field(*, value=INJECTED) -> Any:  # noqa: RUF029
            return value[item]

        async_provide_item_field.__annotations__["value"] = value_type

        return async_provide_item_field


def _add_dependency_type(anno: type) -> None:
    _VARS_BY_DEPENDENCY_TYPE[anno] = ContextVar(anno.__name__)


def _get_dependency_var(anno: type) -> ContextVar:
    return _VARS_BY_DEPENDENCY_TYPE.setdefault(anno, ContextVar(anno.__name__))


_SCOPE_PROVIDER_VARS_BY_DEPENDENCY_TYPE: dict[type, ContextVar[ScopeProvider]] = {}
_VARS_BY_DEPENDENCY_TYPE: WeakKeyDictionary[type, ContextVar] = WeakKeyDictionary()
