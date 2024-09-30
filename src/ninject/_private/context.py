from __future__ import annotations

from contextvars import ContextVar
from typing import TYPE_CHECKING
from typing import Any
from typing import Callable
from typing import Literal
from typing import ParamSpec
from typing import TypedDict
from typing import TypeVar
from typing import Union
from typing import get_args
from typing import get_origin
from typing import overload
from weakref import WeakKeyDictionary

from ninject._private.utils import undefined
from ninject.types import ProviderMissingError

if TYPE_CHECKING:
    from collections.abc import Mapping
    from collections.abc import Sequence
    from contextlib import AsyncExitStack
    from contextlib import ExitStack

    from ninject.types import AsyncContextManagerCallable
    from ninject.types import ContextManagerCallable

P = ParamSpec("P")
R = TypeVar("R")


def setdefault_arguments_with_initialized_dependencies(
    stack: ExitStack | AsyncExitStack,
    arguments: dict[str, Any],
    transient_dependencies: Mapping[str, type],
    singleton_dependencies: Mapping[str, type],
) -> dict[str, type]:
    missing: dict[str, type] = {}
    for name, cls in transient_dependencies.items():
        if (value := arguments.get(name, undefined)) is not undefined:
            set_dependency(stack, cls, value)
        else:
            missing[name] = cls
    for name, cls in singleton_dependencies.items():
        if (value := arguments.get(name, undefined)) is not undefined:
            set_dependency(stack, cls, value)
        elif (value := _get_dependency_var(cls).get(undefined)) is not undefined:
            arguments[name] = value
        else:
            missing[name] = cls
    return missing


def sync_update_arguments_by_initializing_dependencies(
    stack: ExitStack | AsyncExitStack,
    arguments: dict[str, Any],
    dependencies: Mapping[str, type],
) -> None:
    sync_provider_infos = _SYNC_PROVIDER_INFOS.get()
    for name, cls in dependencies.items():
        try:
            provider_info = sync_provider_infos[cls]
        except KeyError:
            # check if there's an async provider
            if async_provider_infos := _ASYNC_PROVIDER_INFOS.get().get(cls):
                msg = f"Async provider {async_provider_infos['manager']} cannot be used in a sync context."
                raise ProviderMissingError(msg) from None
            msg = f"No provider for {cls} is active"
            raise ProviderMissingError(msg) from None

        if provider_info["parent_provider_info"]:
            provider_token = _SYNC_PROVIDER_INFOS.set(
                {**sync_provider_infos, cls: provider_info["parent_provider_info"]}
            )
            stack.callback(_SYNC_PROVIDER_INFOS.reset, provider_token)
        value = arguments[name] = _sync_enter_provider_context(stack, provider_info)
        set_dependency(stack, cls, value)


async def async_update_arguments_by_initializing_dependencies(
    stack: AsyncExitStack,
    arguments: dict[str, Any],
    dependencies: Mapping[str, type],
) -> None:
    missing: dict[str, type] = {}
    async_provider_infos = _ASYNC_PROVIDER_INFOS.get()
    for name, cls in dependencies.items():
        if (provider_info := async_provider_infos.get(cls)) is None:
            missing[name] = cls
        if provider_info["parent_provider_info"]:
            provider_token = _ASYNC_PROVIDER_INFOS.set(
                {**async_provider_infos, cls: provider_info["parent_provider_info"]}
            )
            stack.callback(_ASYNC_PROVIDER_INFOS.reset, provider_token)
        value = arguments[name] = await _async_enter_provider_context(stack, provider_info)
        set_dependency(stack, cls, value)
    sync_update_arguments_by_initializing_dependencies(stack, arguments, missing)


@overload
def set_provider(
    yields: type[R],
    provider: ContextManagerCallable[[], R],
    *,
    sync: Literal[True],
) -> Callable[[], None]: ...


@overload
def set_provider(
    yields: type[R],
    provider: AsyncContextManagerCallable[[], R],
    *,
    sync: Literal[False],
) -> Callable[[], None]: ...


def set_provider(
    yields: type[R],
    manager: ContextManagerCallable[[], R] | AsyncContextManagerCallable[[], R],
    *,
    sync: bool,
) -> Callable[[], None]:
    provider_infos = _SYNC_PROVIDER_INFOS if sync else _ASYNC_PROVIDER_INFOS
    old_provider_infos = provider_infos.get()
    if get_origin(yields) is tuple:
        new_provider_infos = _make_tuple_provider_infos(old_provider_infos, yields, manager, sync=sync)
    else:
        new_provider_infos = _make_scalar_provider_infos(old_provider_infos, yields, manager, sync=sync)
    token = provider_infos.set({**old_provider_infos, **new_provider_infos})
    return lambda: provider_infos.reset(token)


def _make_tuple_provider_infos(
    old: Mapping[type, ProviderInfo],
    yields: tuple,
    manager: ContextManagerCallable[[], R] | AsyncContextManagerCallable[[], R],
    *,
    sync: bool,
) -> dict[type, ProviderInfo]:
    return _make_scalar_provider_infos(old, yields, manager, sync=sync) | {
        item_type: _make_scalar_provider_infos(old, item_type, manager, sync=sync, getter=lambda x, i=index: x[i])
        for index, item_type in enumerate(get_args(yields))
    }


def _make_scalar_provider_infos(
    old: Mapping[type, ProviderInfo],
    yields: type[R],
    manager: ContextManagerCallable[[], R] | AsyncContextManagerCallable[[], R],
    *,
    sync: bool,
    getter: Callable[[R], Any] = lambda x: x,
) -> dict[type, ProviderInfo]:
    if get_origin(yields) is Union:
        return _make_union_provider_infos(old, yields, manager, sync=sync, getter=getter)
    else:
        return {yields: {"manager": manager, "parent_provider_info": old.get(yields), "getter": getter}}


def _make_union_provider_infos(
    old: Mapping[type, ProviderInfo],
    yields: type[R],
    manager: ContextManagerCallable[[], R] | AsyncContextManagerCallable[[], R],
    *,
    sync: bool,
    getter: Callable[[R], Any] = lambda x: x,
) -> dict[type, ProviderInfo]:
    return {cls: _make_scalar_provider_infos(old, cls, manager, sync=sync, getter=getter) for cls in get_args(yields)}


def get_dependency_providers(provider_infos: Mapping[type, ProviderInfo], cls: type[R]) -> Sequence[ProviderInfo[R]]:
    if (provider_info := provider_infos.get(cls)) is None:
        msg = f"No provider for {cls} is active"
        raise ProviderMissingError(msg)
    providers = [provider_info]
    while (parent_provider_info := provider_info["parent_provider_info"]) is not None:
        providers.append(parent_provider_info)
        provider_info = parent_provider_info
    return reversed(providers)


class ProviderInfo(TypedDict):
    manager: ContextManagerCallable[[], Any] | AsyncContextManagerCallable[[], Any]
    parent_provider_info: ProviderInfo | None
    getter: Callable[[Any], Any]


class SyncProviderInfo(ProviderInfo):
    manager: ContextManagerCallable[[], Any]


class AsyncProviderInfo(ProviderInfo):
    manager: AsyncContextManagerCallable[[], Any]


def set_dependency(stack: ExitStack | AsyncExitStack, cls: type[R], value: R) -> None:
    var = _get_dependency_var(cls)
    token = var.set(value)
    stack.callback(var.reset, token)


def _get_dependency_var(cls: type[R]) -> ContextVar[R]:
    """Get the context variable for the dependencies of the given class."""
    if (var := _DEPENDENCIES.get(cls)) is None:
        var = _DEPENDENCIES[cls] = ContextVar(str(cls))
    return var


def _sync_enter_provider_context(stack: ExitStack, provider_info: SyncProviderInfo) -> Any:
    return provider_info["getter"](stack.enter_context(provider_info["manager"]()))


async def _async_enter_provider_context(stack: AsyncExitStack, provider_info: ProviderInfo) -> Any:
    if provider_info["sync"]:
        value = stack.enter_context(provider_info["manager"]())
    else:
        value = await stack.enter_async_context(provider_info["manager"]())
    return provider_info["getter"](value)


_DEPENDENCIES: WeakKeyDictionary[type, ContextVar] = WeakKeyDictionary()
_SYNC_PROVIDER_INFOS: ContextVar[Mapping[type, SyncProviderInfo]] = ContextVar("PROVIDER_INFOS", default={})
_ASYNC_PROVIDER_INFOS: ContextVar[Mapping[type, AsyncProviderInfo]] = ContextVar("PROVIDER_INFOS", default={})
