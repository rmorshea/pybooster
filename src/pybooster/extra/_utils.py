from __future__ import annotations

from typing import TYPE_CHECKING
from typing import Any
from typing import ParamSpec
from typing import TypeVar
from typing import cast

if TYPE_CHECKING:
    from collections.abc import Callable

P = ParamSpec("P")
R = TypeVar("R")


def copy_signature(_: Callable[P, Any]) -> Callable[[Callable[..., R]], Callable[P, R]]:
    def decorator(func: Callable[..., R]) -> Callable[P, R]:
        return cast("Callable[P, R]", func)

    return decorator
