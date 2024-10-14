from __future__ import annotations

import sys
from contextvars import ContextVar
from typing import TYPE_CHECKING
from typing import Any
from typing import Callable
from typing import ParamSpec
from typing import TypeVar

from pybooster.core._private._provider import get_provider_info
from pybooster.core._private._utils import undefined

if TYPE_CHECKING:
    from collections.abc import Awaitable
    from collections.abc import Mapping
    from collections.abc import Sequence


P = ParamSpec("P")
R = TypeVar("R")


def sync_set_shared_context(types: Sequence[type[R]], value: R) -> tuple[R, Callable[[], None]]:
    if value is not undefined:
        reset = _set_shared_value(types, value)
        return value, reset
    else:
        ctx = get_provider_info(types, sync=True)["manager"]()
        value = ctx.__enter__()
        reset = _set_shared_value(types, value)
        return value, lambda: reset() and ctx.__exit__(*sys.exc_info())


async def async_set_shared_context(types: Sequence[type[R]], value: R) -> tuple[R, Callable[[], Awaitable[None]]]:
    if value is not undefined:
        reset = _set_shared_value(types, value)
        return value, reset
    else:
        ctx = get_provider_info(types, sync=False)["manager"]()
        value = await ctx.__aenter__()
        reset = _set_shared_value(types, value)
        return value, lambda: reset() and ctx.__aexit__(*sys.exc_info())


def _set_shared_value(types: Sequence[type[R]], value: R) -> Callable[[], None]:
    token = SHARED_VALUES.set({**SHARED_VALUES.get(), **dict.fromkeys(types, value)})
    return lambda: SHARED_VALUES.reset(token)


SHARED_VALUES: ContextVar[Mapping[type, Any]] = ContextVar("SHARED_VALUES", default={})
