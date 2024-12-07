from __future__ import annotations

from typing import TYPE_CHECKING
from typing import Any
from typing import Literal
from typing import ParamSpec
from typing import TypedDict
from typing import TypeVar
from typing import Union
from typing import cast
from typing import get_args
from typing import get_origin
from typing import overload

from pybooster._private._utils import check_is_concrete_type
from pybooster._private._utils import check_is_not_builtin_type
from pybooster._private._utils import get_raw_annotation
from pybooster._private._utils import is_type
from pybooster.types import AsyncContextManagerCallable
from pybooster.types import ContextManagerCallable
from pybooster.types import Hint
from pybooster.types import HintMap
from pybooster.types import InferHint

if TYPE_CHECKING:
    from collections.abc import Callable
    from collections.abc import Mapping


P = ParamSpec("P")
R = TypeVar("R")


AnyContextManagerCallable = ContextManagerCallable[[], R] | AsyncContextManagerCallable[[], R]


class SyncProviderInfo(TypedDict):
    is_sync: Literal[True]
    producer: ContextManagerCallable[[], Any]
    provides: Hint
    required_parameters: HintMap
    getter: Callable[[Any], Any]


class AsyncProviderInfo(TypedDict):
    is_sync: Literal[False]
    producer: AsyncContextManagerCallable[[], Any]
    provides: Hint
    required_parameters: HintMap
    getter: Callable[[Any], Any]


ProviderInfo = SyncProviderInfo | AsyncProviderInfo


def get_provides_type(provides: Hint | Callable[..., Hint], *args: Any, **kwargs: Any) -> Hint:
    if is_type(provides):
        return provides
    elif callable(provides):
        return provides(*args, **kwargs)
    else:
        check_is_concrete_type(provides)  # might be a TypeVar
        msg = f"Expected a type, or function to infer one, but got {provides!r}."
        raise TypeError(msg)


@overload
def get_provider_info(
    producer: ContextManagerCallable[[], Any],
    provides: Hint | InferHint,
    required_params: HintMap,
    *,
    is_sync: Literal[True],
) -> Mapping[Hint, SyncProviderInfo]: ...


@overload
def get_provider_info(
    producer: AsyncContextManagerCallable[[], Any],
    provides: Hint | InferHint,
    required_params: HintMap,
    *,
    is_sync: Literal[False],
) -> Mapping[Hint, AsyncProviderInfo]: ...


def get_provider_info(
    producer: ContextManagerCallable[[], Any] | AsyncContextManagerCallable[[], Any],
    provides: Hint | InferHint,
    required_params: HintMap,
    *,
    is_sync: bool,
) -> Mapping[Hint, ProviderInfo]:
    provides_type = get_provides_type(provides)
    if get_origin(provides_type) is tuple:
        return _get_tuple_provider_infos(producer, provides_type, required_params, is_sync=is_sync)
    else:
        return _get_scalar_provider_infos(producer, provides_type, required_params, is_sync=is_sync)


def _get_tuple_provider_infos(
    producer: AnyContextManagerCallable,
    provides: Hint,
    required_parameters: HintMap,
    *,
    is_sync: bool,
) -> dict[Hint, ProviderInfo]:
    infos_list = (
        _get_scalar_provider_infos(producer, provides, required_parameters, is_sync=is_sync),
        *(
            _get_scalar_provider_infos(
                producer,
                item_type,
                required_parameters,
                is_sync=is_sync,
                getter=lambda x, i=index: x[i],  # type: ignore[reportIndexIssue]
            )
            for index, item_type in enumerate(get_args(provides))
        ),
    )
    return {c: i for infos in infos_list for c, i in infos.items()}


def _get_scalar_provider_infos(
    producer: AnyContextManagerCallable[R],
    provides: Hint,
    required_parameters: HintMap,
    *,
    is_sync: bool,
    getter: Callable[[R], Any] = lambda x: x,
) -> dict[Hint, ProviderInfo]:
    if get_origin(provides) is Union:
        msg = f"Cannot provide a union type {provides}."
        raise TypeError(msg)

    raw_anno = get_raw_annotation(provides)
    check_is_not_builtin_type(raw_anno)
    check_is_concrete_type(raw_anno)

    info: ProviderInfo
    if is_sync:
        info = SyncProviderInfo(
            is_sync=is_sync,
            producer=cast("ContextManagerCallable[[], Any]", producer),
            provides=provides,
            required_parameters=required_parameters,
            getter=getter,
        )
    else:
        info = AsyncProviderInfo(
            is_sync=is_sync,
            producer=cast("AsyncContextManagerCallable[[], Any]", producer),
            provides=provides,
            required_parameters=required_parameters,
            getter=getter,
        )

    return {provides: info}
