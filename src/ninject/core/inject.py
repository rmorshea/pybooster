from __future__ import annotations

from collections.abc import Mapping
from typing import Callable
from typing import ParamSpec
from typing import TypeVar
from typing import overload

from ninject._private.inspect import get_dependency_defaults_from_callable
from ninject._private.inspect import get_dependency_types_from_callable
from ninject._private.wrapper import make_injection_wrapper

P = ParamSpec("P")
R = TypeVar("R")


@overload
def inject(func: Callable[P, R], /, *, dependencies: Mapping[str, type] | None = ...) -> Callable[P, R]: ...


@overload
def inject(*, dependencies: Mapping[str, type] | None = ...) -> Callable[[Callable[P, R]], Callable[P, R]]: ...


def inject(
    func: Callable[P, R] | None = None,
    *,
    dependencies: Mapping[str, type] | None = None,
) -> Callable[P, R] | Callable[[Callable[P, R]], Callable[P, R]]:
    """Inject values into a function.

    Args:
        func:
            The function to inject values into.
        dependencies:
            A mapping of parameter names to their types. If not provided, then inferred
            from the function signature and type annotations.
    """

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        return make_injection_wrapper(
            func,
            get_dependency_types_from_callable(func) if dependencies is None else dependencies,
            get_dependency_defaults_from_callable(func),
        )

    return decorator(func) if func is not None else decorator
