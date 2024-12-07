from __future__ import annotations

from typing import TYPE_CHECKING
from typing import TypeAlias

from pybooster._private._injector import _CURRENT_VALUES
from pybooster._private._solution import FULL_SOLUTION as _FULL_SOLUTION
from pybooster._private._solution import SYNC_SOLUTION as _SYNC_SOLUTION

if TYPE_CHECKING:
    from collections.abc import Callable


StateResetter: TypeAlias = "Callable[[], None]"
StateSetter: TypeAlias = "Callable[[], StateResetter]"


def copy_state() -> StateSetter:
    """Copy PyBooster's current state and return a callback that will set it in another context.

    Example:
        If you need to run a function in a different context, you can use this function
        to copy the state established there and set it in the new context. This might
        happen if you create a thread (which has its own context) to run a function that
        creates some PyBooster state which you'd then like to use in the main thread.

        ```python
        from concurrent.futures import Future
        from threading import Thread
        from typing import NewType

        from pybooster import injector
        from pybooster.core.state import copy_state

        Greeting = NewType("Greeting", str)


        def from_thread(future):
            with injector.shared((Greeting, "Hello")):
                set_state = copy_state()
                future.set_result(set_state)


        set_state_future = Future()
        thread = Thread(target=from_thread, args=(set_state_future,))
        thread.start()
        set_state = set_state_future.result()

        reset_state = set_state()
        assert injector.current_values().get(Greeting) == "Hello"

        reset_state()
        assert injector.current_values().get(Greeting) is None
        ```
    """
    current_values = _CURRENT_VALUES.get()
    full_solution = _FULL_SOLUTION.get()
    sync_solution = _SYNC_SOLUTION.get()

    def set_state() -> StateResetter:
        current_values_token = _CURRENT_VALUES.set(current_values)
        full_solution_token = _FULL_SOLUTION.set(full_solution)
        sync_solution_token = _SYNC_SOLUTION.set(sync_solution)

        def reset_state() -> None:
            _SYNC_SOLUTION.reset(sync_solution_token)
            _FULL_SOLUTION.reset(full_solution_token)
            _CURRENT_VALUES.reset(current_values_token)

        return reset_state

    return set_state
