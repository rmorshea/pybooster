from __future__ import annotations

from collections.abc import Callable
from typing import Any
from typing import ParamSpec
from typing import TypeVar
from typing import cast

P = ParamSpec("P")
R = TypeVar("R")


def copy_signature(_: Callable[P, Any]) -> Callable[[Callable[..., R]], Callable[P, R]]:
    def decorator(func: Callable[..., R]) -> Callable[P, R]:
        return cast(Callable[P, R], func)

    return decorator
