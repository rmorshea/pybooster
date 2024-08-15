from __future__ import annotations

from collections.abc import Iterator
from collections.abc import Mapping
from contextlib import contextmanager
from typing import Callable
from typing import ParamSpec
from typing import TypeVar
from typing import overload

from ninject._private.inspect import get_scope_params
from ninject._private.scope import ScopeProvider
from ninject._private.scope import make_scope_providers
from ninject._private.scope import set_scope_provider
from ninject._private.utils import exhaust_callbacks
from ninject.types import AnyProvider

P = ParamSpec("P")
R = TypeVar("R")


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
        return Provider(make_scope_providers(get_scope_params(provider, cls, dependencies)))

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
