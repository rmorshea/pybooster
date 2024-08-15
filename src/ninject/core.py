from __future__ import annotations

from collections.abc import Iterator
from collections.abc import Mapping
from contextlib import AbstractAsyncContextManager
from contextlib import AbstractContextManager
from contextlib import contextmanager
from types import TracebackType
from typing import Any
from typing import Callable
from typing import NewType
from typing import ParamSpec
from typing import TypeVar
from typing import get_origin
from typing import overload

from ninject._private.inspect import INJECTED
from ninject._private.inspect import get_dependency_types_from_callable
from ninject._private.inspect import get_scope_params
from ninject._private.scope import ScopeProvider
from ninject._private.scope import get_scope_provider
from ninject._private.scope import make_scope_providers
from ninject._private.scope import set_scope_provider
from ninject._private.utils import exhaust_callbacks
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


@overload
def provider(
    provider: AnyProvider[R],
    /,
    *,
    cls: type[R] | None = ...,
    dependencies: Mapping[str, type] | None = ...,
) -> Provider: ...


@overload
def provider(
    *,
    cls: type[R],
    dependencies: Mapping[str, type] | None = ...,
) -> Callable[[AnyProvider[R]], Provider]: ...


@overload
def provider(
    *,
    dependencies: Mapping[str, type] | None = ...,
) -> Callable[[AnyProvider], Provider]: ...


def provider(
    provider: AnyProvider[R] | None = None,
    /,
    *,
    cls: type[R] | None = None,
    dependencies: Mapping[str, type] | None = None,
) -> Provider | Callable[[AnyProvider[R]], Provider]:
    """Create a provider of a dependency.

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
    """

    def decorator(provider: AnyProvider[R]) -> Provider:
        scope_providers = make_scope_providers(get_scope_params(provider, cls), dependencies)
        return Provider(scope_providers)

    return decorator(provider) if provider is not None else decorator


class Provider:
    """A provider of one or more dependencies."""

    def __init__(self, scope_providers: Mapping[type, ScopeProvider]) -> None:
        self._scope_providers = scope_providers

    def __or__(self, other: Provider) -> Provider:
        return Provider({**self._scope_providers, **other._scope_providers})

    @contextmanager
    def __call__(self) -> Iterator[None]:
        reset_callbacks = [set_scope_provider(t, p) for t, p in self._scope_providers.items()]
        try:
            yield
        finally:
            exhaust_callbacks(reset_callbacks)

    def __repr__(self) -> str:
        body = ", ".join([t.__qualname__ for t in self._scope_providers])
        return f"{self.__class__.__name__}({body})"


class current(AbstractContextManager[T], AbstractAsyncContextManager[T]):  # noqa: N801
    """A context manager to provide the current value of a dependency."""

    def __init__(self, cls: type[T]) -> None:
        self._scope_provider = get_scope_provider(cls)

    def __enter__(self) -> T:
        self._sync_scope = self._scope_provider()
        return self._sync_scope.__enter__()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._sync_scope.__exit__(exc_type, exc_value, traceback)
        del self._sync_scope

    async def __aenter__(self) -> T:
        self._async_scope = self._scope_provider()
        return await self._async_scope.__aenter__()

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self._async_scope.__aexit__(exc_type, exc_value, traceback)
        del self._async_scope
