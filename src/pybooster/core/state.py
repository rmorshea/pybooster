from __future__ import annotations

from typing import TYPE_CHECKING

from pybooster._private._injector import _CURRENT_VALUES
from pybooster._private._solution import FULL_SOLUTION as _FULL_SOLUTION
from pybooster._private._solution import SYNC_SOLUTION as _SYNC_SOLUTION

if TYPE_CHECKING:
    from collections.abc import Callable


def copy_state() -> Callable[[], None]:
    """Copy PyBooster's current state and return a callback that will set it in another context."""
    current_values = _CURRENT_VALUES.get()
    full_solution = _FULL_SOLUTION.get()
    sync_solution = _SYNC_SOLUTION.get()

    def set_state() -> None:
        _CURRENT_VALUES.set(current_values)
        _FULL_SOLUTION.set(full_solution)
        _SYNC_SOLUTION.set(sync_solution)

    return set_state
