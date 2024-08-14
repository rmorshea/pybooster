from __future__ import annotations

from collections.abc import Iterator
from collections.abc import Mapping
from contextlib import contextmanager
from typing import Any
from typing import Callable
from typing import Literal
from typing import NewType
from typing import ParamSpec
from typing import TypeVar
from typing import get_origin
from typing import overload

from typing_extensions import Self

from ninject._private.inspect import INJECTED
from ninject._private.inspect import get_dependency_types_from_callable
from ninject._private.inspect import get_scope_params
from ninject._private.scope import ScopeProvider
from ninject._private.scope import make_scope_providers
from ninject._private.scope import set_scope_provider
from ninject._private.wrapper import make_injection_wrapper
from ninject.types import AnyProvider

P = ParamSpec("P")
R = TypeVar("R")
T = TypeVar("T")


class Inject:
    """A decorator to inject values into a function."""

    ed = INJECTED
    """A sentinel value to indicate that a parameter should be injected."""

    def __call__(self, func: Callable[P, R], *, dependencies: Mapping[str, type] | None = None) -> Callable[P, R]:
        """Inject values into a function.

        Args:
            func:
                The function to inject values into.
            dependencies:
                A mapping of parameter names to their types. If not provided, then inferred
                from the function signature and type annotations.
        """
        dependencies = get_dependency_types_from_callable(func) if dependencies is None else dependencies
        return make_injection_wrapper(func, dependencies)

    def __repr__(self) -> str:
        return "inject()"


inject = Inject()
"""A decorator to inject values into a function."""
del Inject


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


class Context:
    """A context manager for setting provider functions."""

    def __init__(self, other: Context | None = None) -> None:
        self._context_providers: dict[type, ScopeProvider] = other._context_providers.copy() if other else {}

    def copy(self) -> Self:
        """Return a shallow copy of the context."""
        return self.__class__(self)

    @overload
    def provides(
        self,
        provider: AnyProvider[R],
        /,
        *,
        cls: type[R] | None = ...,
        dependencies: Mapping[str, type] | None = ...,
        on_conflict: Literal["raise", "replace"] = ...,
    ) -> AnyProvider[R]: ...

    @overload
    def provides(
        self,
        *,
        cls: type[R],
        dependencies: Mapping[str, type] | None = ...,
        on_conflict: Literal["raise", "replace"] = ...,
    ) -> Callable[[AnyProvider[R]], AnyProvider[R]]: ...

    @overload
    def provides(
        self,
        *,
        dependencies: Mapping[str, type] | None = ...,
        on_conflict: Literal["raise", "replace"] = ...,
    ) -> Callable[[AnyProvider[R]], AnyProvider[R]]: ...

    def provides(
        self,
        provider: AnyProvider[R] | None = None,
        *,
        cls: type[R] | None = None,
        dependencies: Mapping[str, type] | None = None,
        on_conflict: Literal["raise", "replace"] = "raise",
    ) -> AnyProvider[R] | Callable[[AnyProvider[R]], AnyProvider[R]]:
        """Add a provider function.

        Args:
            provider:
                The provider of a depdency. A function that returns the dependency,
                a generator that yields the dependency, or a context manager that
                does.
            cls:
                The type to provide. If not provided, then inferred from provider return
                type annotation.
            dependencies:
                A mapping of required parameter names to their types. If not provided,
                then inferred from provider signature and type annotations.
            on_conflict:
                The action to take when a provider function is already defined for the
                `cls`. If "raise", then raise a `TypeError`. If "replace", then override
                the existing provider function.
        """

        def decorator(provider: AnyProvider[R]) -> AnyProvider[R]:
            params = get_scope_params(provider, cls)

            providers = make_scope_providers(params, dependencies)
            if on_conflict == "raise" and (conflicts := self._context_providers.keys() & providers.keys()):
                msg = f"Providers already defined for {conflicts} in this context."
                raise TypeError(msg)
            self._context_providers.update(providers)

            return provider

        return decorator if provider is None else decorator(provider)

    def __enter__(self) -> None:
        self._reset_callbacks = [set_scope_provider(t, p) for t, p in self._context_providers.items()]

    def __exit__(self, etype: Any, evalue: Any, atrace: Any, /) -> None:
        try:
            for reset in self._reset_callbacks:
                reset()
        finally:
            del self._reset_callbacks

    def __repr__(self) -> str:
        body = ", ".join(map(repr, self._context_providers))
        return f"{self.__class__.__name__}({body})"
