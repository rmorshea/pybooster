from __future__ import annotations

from typing import TYPE_CHECKING
from typing import Any

from pybooster.core._private._injector import CURRENT_VALUES as _CURRENT_VALUES
from pybooster.core._private._solution import _FULL_INFOS
from pybooster.core._private._solution import _FULL_SOLUTION
from pybooster.core._private._solution import _SYNC_INFOS
from pybooster.core._private._solution import _SYNC_SOLUTION

if TYPE_CHECKING:
    from collections.abc import Mapping
    from contextvars import ContextVar


def copy_state() -> State:
    state = State()
    state._context_ = {
        _CURRENT_VALUES: _CURRENT_VALUES.get(),
        _FULL_INFOS: _FULL_INFOS.get(),
        _SYNC_INFOS: _SYNC_INFOS.get(),
        _FULL_SOLUTION: _FULL_SOLUTION.get(),
        _SYNC_SOLUTION: _SYNC_SOLUTION.get(),
    }
    return state


class State:
    """PyBooster's internal state."""

    _context_: Mapping[ContextVar, Any]

    def restore(self) -> None:
        """Restore PyBooster's state from some prior time."""
        for var, val in self._context_.items():
            var.set(val)
