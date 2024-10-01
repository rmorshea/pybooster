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

from ninject.types import ProviderMissingError

if TYPE_CHECKING:
    from collections.abc import Mapping

    from ninject.types import AsyncContextManagerCallable
    from ninject.types import ContextManagerCallable

P = ParamSpec("P")
R = TypeVar("R")


@overload
def set_provider(
    provides: type[R],
    provider: ContextManagerCallable[[], R],
    dependencies: set[type],
    *,
    sync: Literal[True],
    singleton: bool,
) -> Callable[[], None]: ...


@overload
def set_provider(
    provides: type[R],
    provider: AsyncContextManagerCallable[[], R],
    dependencies: set[type],
    *,
    sync: Literal[False],
    singleton: bool,
) -> Callable[[], None]: ...


def set_provider(
    provides: type[R],
    manager: ContextManagerCallable[[], R] | AsyncContextManagerCallable[[], R],
    dependencies: set[type],
    *,
    sync: bool,
    singleton: bool,
) -> Callable[[], None]:
    active_providers = SYNC_PROVIDER_INFOS.get() if sync else ASYNC_PROVIDER_INFOS.get() | SYNC_PROVIDER_INFOS.get()
    if missing := dependencies.difference(active_providers):
        msg = f"No active {'sync' if sync else 'sync or async'} providers for {missing}"
        raise ProviderMissingError(msg)

    if get_origin(provides) is tuple:
        new_provider_infos = _make_tuple_provider_infos(provides, manager, sync=sync, singleton=singleton)
    else:
        new_provider_infos = _make_scalar_provider_infos(provides, manager, sync=sync, singleton=singleton)

    provider_infos = SYNC_PROVIDER_INFOS if sync else ASYNC_PROVIDER_INFOS
    token = provider_infos.set({**active_providers, **new_provider_infos})
    return lambda: provider_infos.reset(token)


class ProviderInfo(TypedDict):
    manager: ContextManagerCallable[[], Any] | AsyncContextManagerCallable[[], Any]
    getter: Callable[[Any], Any]
    singleton: bool


class SyncProviderInfo(ProviderInfo):
    manager: ContextManagerCallable[[], Any]


class AsyncProviderInfo(ProviderInfo):
    manager: AsyncContextManagerCallable[[], Any]


def _make_tuple_provider_infos(
    provides: tuple,
    manager: ContextManagerCallable[[], R] | AsyncContextManagerCallable[[], R],
    *,
    sync: bool,
    singleton: bool,
) -> dict[type, ProviderInfo]:
    return _make_scalar_provider_infos(provides, manager, sync=sync, singleton=singleton) | {
        item_type: _make_scalar_provider_infos(
            item_type,
            manager,
            sync=sync,
            singleton=singleton,
            getter=lambda x, i=index: x[i],
        )
        for index, item_type in enumerate(get_args(provides))
    }


def _make_scalar_provider_infos(
    provides: type[R],
    manager: ContextManagerCallable[[], R] | AsyncContextManagerCallable[[], R],
    *,
    sync: bool,
    singleton: bool,
    getter: Callable[[R], Any] = lambda x: x,
) -> dict[type, ProviderInfo]:
    if get_origin(provides) is Union:
        return _make_union_provider_infos(provides, manager, sync=sync, getter=getter, singleton=singleton)
    else:
        return {provides: {"manager": manager, "getter": getter, "singleton": singleton}}


def _make_union_provider_infos(
    provides: type[R],
    manager: ContextManagerCallable[[], R] | AsyncContextManagerCallable[[], R],
    *,
    sync: bool,
    singleton: bool,
    getter: Callable[[R], Any] = lambda x: x,
) -> dict[type, ProviderInfo]:
    return {
        cls: _make_scalar_provider_infos(cls, manager, sync=sync, getter=getter, singleton=singleton)
        for cls in get_args(provides)
    }


SYNC_PROVIDER_INFOS: ContextVar[Mapping[type, SyncProviderInfo]] = ContextVar("PROVIDER_INFOS", default={})
ASYNC_PROVIDER_INFOS: ContextVar[Mapping[type, AsyncProviderInfo]] = ContextVar("PROVIDER_INFOS", default={})
