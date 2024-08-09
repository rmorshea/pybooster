from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, Callable, NewType, ParamSpec, TypeVar, get_args, get_origin, overload

from ninject._dependency import (
    AsyncDependencyContext,
    DependencyContextProvider,
    SyncDependencyContext,
    add_dependency_type,
    get_dependency_name,
    get_dependency_value_var,
    set_dependency_context_provider,
)
from ninject._inspect import (
    INJECTED,
    AsyncProviderInfo,
    ProviderInfo,
    get_caller_module_name,
    get_injected_dependency_types_from_callable,
    get_provider_info,
)
from ninject._provider import make_context_providers
from ninject._wrapper import make_injection_wrapper
from ninject.types import AnyProvider

P = ParamSpec("P")
R = TypeVar("R")


if TYPE_CHECKING:
    Dependency = NewType
else:

    def Dependency(name, tp):  # noqa: N802
        new_type = NewType(name, tp)
        new_type.__module__ = get_caller_module_name()
        add_dependency_type(name, new_type)
        return new_type


class Inject:
    """A decorator to inject values into a function."""

    ed = INJECTED
    """A sentinel value to indicate that a parameter should be injected."""

    def __call__(self, func: Callable[P, R], *, dependencies: Mapping[str, type] | None = None) -> Callable[P, R]:
        """Inject values into a function."""
        dependencies = get_injected_dependency_types_from_callable(func) if dependencies is None else dependencies
        return make_injection_wrapper(func, dependencies)

    def __repr__(self) -> str:
        return "inject()"


inject = Inject()
"""A decorator to inject values into a function."""
del Inject


@contextmanager
def let(cls: type[R], value: R) -> Iterator[R]:
    """Set the value of a dependency for the duration of the context."""
    var = get_dependency_value_var(cls)  # Ensure the provider exists
    reset_token = var.set(value)
    try:
        yield value
    finally:
        var.reset(reset_token)


class Context:
    """A context manager for setting provider functions."""

    def __init__(self) -> None:
        self._context_providers: dict[type, DependencyContextProvider] = {}

    @overload
    def provides(
        self,
        provider: AnyProvider[R],
        /,
        *,
        cls: type[R] | None = ...,
        dependencies: Mapping[str, type] | None = ...,
    ) -> AnyProvider[R]: ...

    @overload
    def provides(
        self,
        *,
        cls: type[R],
        dependencies: Mapping[str, type] | None = ...,
    ) -> Callable[[AnyProvider[R]], AnyProvider[R]]: ...

    @overload
    def provides(
        self,
        *,
        dependencies: Mapping[str, type] | None = ...,
    ) -> Callable[[AnyProvider[R]], AnyProvider[R]]: ...

    def provides(
        self,
        provider: AnyProvider[R] | None = None,
        *,
        cls: type[R] | None = None,
        dependencies: Mapping[str, type] | None = None,
    ) -> AnyProvider[R] | Callable[[AnyProvider[R]], AnyProvider[R]]:
        """Add a provider function."""

        def decorator(provider: AnyProvider[R]) -> AnyProvider[R]:
            info = get_provider_info(provider, cls)

            providers = make_context_providers(info, dependencies)
            if conflicts := self._context_providers.keys() & providers.keys():
                msg = f"Providers already defined for {conflicts}"
                raise RuntimeError(msg)
            self._context_providers.update(providers)

            return provider

        return decorator if provider is None else decorator(provider)

    def __enter__(self) -> None:
        self._reset_callbacks = [set_dependency_context_provider(v, p) for v, p in self._context_providers.items()]

    def __exit__(self, etype: Any, evalue: Any, atrace: Any, /) -> None:
        try:
            for reset in self._reset_callbacks:
                reset()
        finally:
            del self._reset_callbacks

    def __repr__(self) -> str:
        body = ", ".join(map(repr, self._context_providers))
        return f"{self.__class__.__name__}({body})"
