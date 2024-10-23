from __future__ import annotations

from typing import Callable

from pybooster.core._private._injector import CURRENT_VALUES as _CURRENT_VALUES
from pybooster.core._private._solution import _FULL_SOLUTION
from pybooster.core._private._solution import _SYNC_SOLUTION


def copy_state() -> Callable[[], None]:
    """Copy PyBooster's current state and return a callback that will restore it in another context."""
    current_values = _CURRENT_VALUES.get()
    full_solution = _FULL_SOLUTION.get()
    sync_solution = _SYNC_SOLUTION.get()

    def restore() -> None:
        _CURRENT_VALUES.set(current_values)
        _FULL_SOLUTION.set(full_solution)
        _SYNC_SOLUTION.set(sync_solution)

    return restore
