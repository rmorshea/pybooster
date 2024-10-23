from __future__ import annotations

from typing import TYPE_CHECKING
from typing import Any
from typing import Callable
from typing import Literal
from typing import ParamSpec
from typing import TypedDict
from typing import TypeVar
from typing import Union
from typing import cast
from typing import get_args
from typing import get_origin
from typing import overload

from pybooster.core._private._utils import is_type
from pybooster.core.types import AsyncContextManagerCallable
from pybooster.core.types import ContextManagerCallable

if TYPE_CHECKING:
    from collections.abc import Sequence

    from pybooster.core._private._utils import NormDependencies

P = ParamSpec("P")
R = TypeVar("R")


AnyContextManagerCallable = ContextManagerCallable[[], R] | AsyncContextManagerCallable[[], R]


class SyncProviderInfo(TypedDict):
    is_sync: Literal[True]
    producer: ContextManagerCallable[[], Any]
    provides: type
    dependencies: set[type]
    getter: Callable[[Any], Any]


class AsyncProviderInfo(TypedDict):
    is_sync: Literal[False]
    producer: AsyncContextManagerCallable[[], Any]
    provides: type
    dependencies: set[type]
    getter: Callable[[Any], Any]


ProviderInfo = SyncProviderInfo | AsyncProviderInfo


def get_provides_type(provides: type[R] | Callable[..., type[R]], *args: Any, **kwargs: Any) -> type[R]:
    if is_type(provides):
        return cast(type[R], provides)
    elif callable(provides):
        return provides(*args, **kwargs)
    else:
        msg = f"Expected a type, or function to infer one, but got {provides}."
        raise TypeError(msg)


@overload
def get_provider_info(
    producer: ContextManagerCallable[[], R],
    provides: type[R] | Callable[[], type[R]],
    dependencies: NormDependencies,
    *,
    is_sync: Literal[True],
) -> SyncProviderInfo: ...


@overload
def get_provider_info(
    producer: AsyncContextManagerCallable[[], R],
    provides: type[R] | Callable[[], type[R]],
    dependencies: NormDependencies,
    *,
    is_sync: Literal[False],
) -> AsyncProviderInfo: ...


def get_provider_info(
    producer: ContextManagerCallable[[], R] | AsyncContextManagerCallable[[], R],
    provides: type[R] | Callable[[], type[R]],
    dependencies: NormDependencies,
    *,
    is_sync: bool,
) -> ProviderInfo:
    provides_type = get_provides_type(provides)
    dependency_types = [t for types in dependencies.values() for t in types]
    if get_origin(provides_type) is tuple:
        return _get_tuple_provider_infos(producer, provides_type, dependency_types, is_sync=is_sync)
    else:
        return _get_scalar_provider_infos(producer, provides_type, dependency_types, is_sync=is_sync)


def _get_tuple_provider_infos(
    producer: AnyContextManagerCallable[R],
    provides: type[R],
    dependencies: Sequence[type],
    *,
    is_sync: bool,
) -> dict[type, ProviderInfo]:
    infos_list = (
        _get_scalar_provider_infos(producer, provides, dependencies, is_sync=is_sync),
        *(
            _get_scalar_provider_infos(
                producer,
                item_type,
                dependencies,
                is_sync=is_sync,
                getter=lambda x, i=index: x[i],  # type: ignore[reportIndexIssue]
            )
            for index, item_type in enumerate(get_args(provides))
        ),
    )
    return {c: i for infos in infos_list for c, i in infos.items()}


def _get_scalar_provider_infos(
    producer: AnyContextManagerCallable[R],
    provides: type[R],
    dependencies: Sequence[type],
    *,
    is_sync: bool,
    getter: Callable[[R], Any] = lambda x: x,
) -> dict[type, ProviderInfo]:
    if get_origin(provides) is Union:
        msg = f"Cannot provide a union type {provides}."
        raise TypeError(msg)

    if hasattr(provides, "__mro__"):
        return {
            cls: cast(
                ProviderInfo,
                {
                    "is_sync": is_sync,
                    "producer": producer,
                    "provides": cls,
                    "dependencies": set(dependencies),
                    "getter": getter,
                },
            )
            for cls in provides.__mro__
        }
    else:
        return {
            provides: cast(
                ProviderInfo,
                {
                    "is_sync": is_sync,
                    "producer": producer,
                    "provides": provides,
                    "dependencies": set(dependencies),
                    "getter": getter,
                },
            )
        }
