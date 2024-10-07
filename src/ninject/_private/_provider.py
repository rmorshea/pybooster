from __future__ import annotations

from contextvars import ContextVar
from typing import TYPE_CHECKING
from typing import Any
from typing import Callable
from typing import Literal
from typing import NoReturn
from typing import ParamSpec
from typing import TypedDict
from typing import TypeVar
from typing import Union
from typing import get_args
from typing import get_origin
from typing import overload

from ninject.types import ProviderMissingError

if TYPE_CHECKING:
    from collections.abc import Collection
    from collections.abc import Mapping

    from ninject.types import AsyncContextManagerCallable
    from ninject.types import ContextManagerCallable

P = ParamSpec("P")
R = TypeVar("R")


def raise_missing_provider(types: Collection[type], *, sync_context: bool) -> NoReturn:
    sync_msg = "sync" if sync_context else "sync or async"
    type_msg = f"any of {types}" if len(types) > 1 else f"{types[0]}"
    msg = f"No {sync_msg} provider for {type_msg}"
    raise ProviderMissingError(msg) from None


@overload
def set_provider(
    provides: type[R],
    provider: ContextManagerCallable[[], R],
    dependencies: set[type],
    *,
    sync: Literal[True],
) -> Callable[[], None]: ...


@overload
def set_provider(
    provides: type[R],
    provider: AsyncContextManagerCallable[[], R],
    dependencies: set[type],
    *,
    sync: Literal[False],
) -> Callable[[], None]: ...


def set_provider(
    provides: type[R],
    manager: ContextManagerCallable[[], R] | AsyncContextManagerCallable[[], R],
    dependencies: set[type],
    *,
    sync: bool,
) -> Callable[[], None]:
    provider_infos_var = SYNC_PROVIDER_INFOS if sync else SYNC_OR_ASYNC_PROVIDER_INFOS
    prior_provider_infos = provider_infos_var.get()
    if missing := dependencies.difference(prior_provider_infos):
        raise_missing_provider(missing, sync_context=sync)

    if get_origin(provides) is tuple:
        new_provider_infos = _make_tuple_provider_infos(provides, manager, sync=sync)
    else:
        new_provider_infos = _make_scalar_provider_infos(provides, manager, sync=sync)

    next_provider_infos: dict[type, ProviderInfo] = dict(prior_provider_infos)
    for cls, provider_info in new_provider_infos.items():
        if isinstance(cls, type):
            mro_without_builtins = filter(lambda c: c.__module__ != "builtins", cls.mro())
            next_provider_infos.update(dict.fromkeys(mro_without_builtins, provider_info))
        else:
            next_provider_infos[cls] = provider_info

    token = provider_infos_var.set(next_provider_infos)
    return lambda: provider_infos_var.reset(token)


class _BaseProviderInfo(TypedDict):
    manager: ContextManagerCallable[[], Any] | AsyncContextManagerCallable[[], Any]
    getter: Callable[[Any], Any]
    sync: bool


class SyncProviderInfo(_BaseProviderInfo):
    manager: ContextManagerCallable[[], Any]
    sync: Literal[True]


class AsyncProviderInfo(_BaseProviderInfo):
    manager: AsyncContextManagerCallable[[], Any]
    sync: Literal[False]


ProviderInfo = SyncProviderInfo | AsyncProviderInfo


def _make_tuple_provider_infos(
    provides: tuple,
    manager: ContextManagerCallable[[], R] | AsyncContextManagerCallable[[], R],
    *,
    sync: bool,
) -> dict[type, ProviderInfo]:
    return _make_scalar_provider_infos(provides, manager, sync=sync) | {
        item_type: _make_scalar_provider_infos(
            item_type,
            manager,
            sync=sync,
            getter=lambda x, i=index: x[i],
        )
        for index, item_type in enumerate(get_args(provides))
    }


def _make_scalar_provider_infos(
    provides: type[R],
    manager: ContextManagerCallable[[], R] | AsyncContextManagerCallable[[], R],
    *,
    sync: bool,
    getter: Callable[[R], Any] = lambda x: x,
) -> dict[type, ProviderInfo]:
    if get_origin(provides) is Union:
        msg = f"Cannot provide a union type {provides}."
        raise TypeError(msg)
    if isinstance(provides, type) and provides.__module__ == "builtins":
        msg = f"Cannot provide built-in type {provides} - use NewType to make a distinct subtype."
        raise TypeError(msg)
    return {provides: {"manager": manager, "getter": getter, "sync": sync}}


SYNC_PROVIDER_INFOS: ContextVar[Mapping[type, SyncProviderInfo]] = ContextVar("PROVIDER_INFOS", default={})
SYNC_OR_ASYNC_PROVIDER_INFOS: ContextVar[Mapping[type, ProviderInfo]] = ContextVar("PROVIDER_INFOS", default={})
