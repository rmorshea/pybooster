from __future__ import annotations

from collections.abc import Mapping
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
from typing import cast
from typing import get_args
from typing import get_origin
from typing import overload

from pybooster._private._utils import check_is_concrete_type
from pybooster.types import ProviderMissingError

if TYPE_CHECKING:
    from collections.abc import Collection
    from collections.abc import Iterator
    from collections.abc import Mapping
    from collections.abc import Sequence

    from pybooster._private._utils import NormDependencies
    from pybooster.types import AsyncContextManagerCallable
    from pybooster.types import ContextManagerCallable

P = ParamSpec("P")
R = TypeVar("R")


def raise_missing_provider(types: Collection[type], *, sync: bool) -> NoReturn:
    sync_msg = "sync" if sync else "sync or async"
    type_msg = f"any of {types}" if len(types) > 1 else f"{next(iter(types))}"
    msg = f"No {sync_msg} provider for {type_msg}"
    raise ProviderMissingError(msg)


@overload
def iter_provider_infos(
    dependencies: NormDependencies, *, sync: Literal[True]
) -> Iterator[tuple[str, type, SyncProviderInfo]]: ...


@overload
def iter_provider_infos(dependencies: NormDependencies, *, sync: bool) -> Iterator[tuple[str, type, ProviderInfo]]: ...


def iter_provider_infos(dependencies: NormDependencies, *, sync: bool) -> Iterator[tuple[str, type, ProviderInfo]]:
    provider_infos = get_all_provider_infos(sync=sync)
    for name, types in dependencies.items():
        for cls in types:
            if (info := provider_infos.get(cls)) is not None:
                break
        else:
            raise_missing_provider(types, sync=sync)
        yield name, cls, info


@overload
def get_provider_info(types: Sequence[type], *, sync: Literal[True]) -> SyncProviderInfo: ...


@overload
def get_provider_info(types: Sequence[type], *, sync: Literal[False]) -> AsyncProviderInfo: ...


def get_provider_info(types: Sequence[type], *, sync: bool) -> ProviderInfo:
    provider_infos = get_all_provider_infos(sync=sync)
    for cls in types:
        if (info := provider_infos.get(cls)) is not None:
            return info
    raise_missing_provider(types, sync=sync)


def get_all_provider_infos(*, sync: bool) -> Mapping[type, ProviderInfo]:
    return _SYNC_PROVIDER_INFOS.get() if sync else {**_SYNC_PROVIDER_INFOS.get(), **_ASYNC_PROVIDER_INFOS.get()}


def set_provider(
    provides: type[R],
    manager: ContextManagerCallable[[], R] | AsyncContextManagerCallable[[], R],
    dependency_set: set[Sequence[type]],
    *,
    sync: bool,
) -> Callable[[], None]:
    check_is_concrete_type(provides)
    _check_missing_dependencies(dependency_set, sync=sync)

    provider_infos_var = _SYNC_PROVIDER_INFOS if sync else _ASYNC_PROVIDER_INFOS
    prior_provider_infos = provider_infos_var.get()

    if get_origin(provides) is tuple:
        new_provider_infos = _make_tuple_provider_infos(provides, manager, sync=sync)
    else:
        new_provider_infos = _make_scalar_provider_infos(provides, manager, sync=sync)

    next_provider_infos = dict(prior_provider_infos)
    for cls, provider_info in new_provider_infos.items():
        if isinstance(cls, type):
            mro_without_builtins = filter(lambda c: c.__module__ != "builtins", cls.mro())
            next_provider_infos.update(dict.fromkeys(mro_without_builtins, provider_info))
        else:
            next_provider_infos[cls] = provider_info

    token = provider_infos_var.set(next_provider_infos)  # type: ignore[reportArgumentType]
    return lambda: provider_infos_var.reset(token)  # type: ignore[reportArgumentType]


def _check_missing_dependencies(dependency_set: set[Sequence[type]], *, sync: bool) -> None:
    provider_infos = get_all_provider_infos(sync=sync)
    missing: set[type] = set()
    for types in dependency_set:
        missing.update(set(types) - provider_infos.keys())
    if missing:
        raise_missing_provider(missing, sync=sync)


class SyncProviderInfo(TypedDict):
    sync: Literal[True]
    manager: ContextManagerCallable[[], Any]
    getter: Callable[[Any], Any]


class AsyncProviderInfo(TypedDict):
    sync: Literal[False]
    manager: AsyncContextManagerCallable[[], Any]
    getter: Callable[[Any], Any]


ProviderInfo = SyncProviderInfo | AsyncProviderInfo


def _make_tuple_provider_infos(
    provides: Any,
    manager: ContextManagerCallable[[], Any] | AsyncContextManagerCallable[[], Any],
    *,
    sync: bool,
) -> dict[type, ProviderInfo]:
    infos_list = (
        _make_scalar_provider_infos(provides, manager, sync=sync),
        *(
            _make_scalar_provider_infos(
                item_type,
                manager,
                sync=sync,
                getter=lambda x, i=index: x[i],  # type: ignore[reportIndexIssue]
            )
            for index, item_type in enumerate(get_args(provides))
        ),
    )
    return {c: i for infos in infos_list for c, i in infos.items()}


def _make_scalar_provider_infos(
    provides: Any,
    manager: ContextManagerCallable[[], Any] | AsyncContextManagerCallable[[], Any],
    *,
    sync: bool,
    getter: Callable[[R], Any] = lambda x: x,
) -> dict[type, ProviderInfo]:
    if get_origin(provides) is Union:
        msg = f"Cannot provide a union type {provides}."
        raise TypeError(msg)
    return {provides: cast(ProviderInfo, {"manager": manager, "getter": getter, "sync": sync})}


_SYNC_PROVIDER_INFOS: ContextVar[Mapping[type, SyncProviderInfo]] = ContextVar("SYNC_PROVIDER_INFOS", default={})
_ASYNC_PROVIDER_INFOS: ContextVar[Mapping[type, AsyncProviderInfo]] = ContextVar("ASYNC_PROVIDER_INFOS", default={})
