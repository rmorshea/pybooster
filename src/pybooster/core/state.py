from __future__ import annotations

from typing import Callable

from pybooster.core._private._provider import _ASYNC_PROVIDER_INFOS
from pybooster.core._private._provider import _SYNC_PROVIDER_INFOS
from pybooster.core._private._shared import SHARED_VALUES as _SHARED_VALUES


def copy_state() -> Callable[[], None]:
    """Copy the internal state of PyBooster from the current context and return a function to restore it in another."""
    context = {
        _SHARED_VALUES: _SHARED_VALUES.get(),
        _SYNC_PROVIDER_INFOS: _SYNC_PROVIDER_INFOS.get(),
        _ASYNC_PROVIDER_INFOS: _ASYNC_PROVIDER_INFOS.get(),
    }

    def restore():
        for var, val in context.items():
            var.set(val)

    return restore
