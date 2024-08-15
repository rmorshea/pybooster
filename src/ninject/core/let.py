from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from typing import Callable
from typing import NewType
from typing import TypeVar
from typing import get_origin
from typing import overload

from ninject._private.inspect import get_scope_params
from ninject._private.scope import make_scope_providers
from ninject._private.scope import set_scope_provider

R = TypeVar("R")
T = TypeVar("T")


@overload
def _let(value: R, /) -> Iterator[R]: ...


@overload
def _let(cls: Callable[[T], R], value: T, /) -> Iterator[R]: ...


def _let(*args: Any) -> Iterator[Any]:
    if len(args) == 1:
        value = args[0]
        cls = type(value)
    else:
        cls, value = args
        if get_origin(cls) is None and not isinstance(cls, (type, NewType)):
            msg = f"Expected type, got {cls!r}"
            raise TypeError(msg)

    scope_providers = make_scope_providers(get_scope_params(lambda: value, cls), {})
    reset_callbacks = [set_scope_provider(t, p) for t, p in scope_providers.items()]
    try:
        yield value
    finally:
        for reset in reset_callbacks:
            reset()


let = contextmanager(_let)
"""Set the value of a dependency for the duration of the context.

Examples:
    For user-defined types:

    ```python
    from dataclasses import dataclass

    @dataclass
    class Config:
        greeting: str
        recipient: str

    with let(Config("Hello", "World")):
        ...
    ```

    When a type alias or `NewType` is used to define a dependency:

    ```python
    from typing import NewType

    Greeting = NewType("Greeting", str)
    Recipient = NewType("Recipient", str)

    with (
        let(Greeting, "Hello"),
        let(Recipient, "World"),
    ):
        ...
    ```
"""
