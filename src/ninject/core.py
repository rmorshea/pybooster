from __future__ import annotations

from collections.abc import Mapping
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    NewType,
    ParamSpec,
    TypeVar,
    overload,
)

from ninject._private import (
    INJECTED,
    ProviderInfo,
    SyncProviderInfo,
    UniformContextProvider,
    add_dependency,
    get_caller_module_name,
    get_injected_dependency_types_from_callable,
    get_provider_info,
    make_context_provider,
    make_injection_wrapper,
    make_item_provider,
    set_context_provider,
)
from ninject.types import AnyProvider

P = ParamSpec("P")
R = TypeVar("R")


if TYPE_CHECKING:
    Dependency = NewType
else:

    def Dependency(name, tp):  # noqa: N802
        new_type = NewType(name, tp)
        new_type.__module__ = get_caller_module_name()
        add_dependency(new_type)
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


class Context:
    """A context manager for setting provider functions."""

    def __init__(self) -> None:
        self._context_providers: dict[type, UniformContextProvider] = {}

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
            provider_info = get_provider_info(provider, cls)

            if not provider_info.container_info:
                self._provides_one(provider_info, dependencies)
            else:
                add_dependency(provider_info.type)
                self._provides_one(provider_info, dependencies)
                from_obj = provider_info.container_info.kind == "obj"
                is_sync = isinstance(provider_info, SyncProviderInfo)
                for dep_key, dep_type in provider_info.container_info.dependencies.items():
                    item_provider = make_item_provider(dep_key, provider_info.type, is_sync=is_sync, from_obj=from_obj)
                    self.provides(item_provider, cls=dep_type, dependencies={"value": provider_info.type})

            return provider

        return decorator if provider is None else decorator(provider)

    def _provides_one(self, info: ProviderInfo[Any], dependencies: Mapping[str, type] | None) -> None:
        if info.type in self._context_providers:
            msg = f"Provider for {info.type} has already been set"
            raise RuntimeError(msg)
        self._context_providers[info.type] = make_context_provider(info, dependencies)

    def __enter__(self) -> None:
        self._reset_callbacks = [set_context_provider(v, p) for v, p in self._context_providers.items()]

    def __exit__(self, etype: Any, evalue: Any, atrace: Any, /) -> None:
        try:
            for reset in self._reset_callbacks:
                reset()
        finally:
            del self._reset_callbacks

    def __repr__(self) -> str:
        body = ", ".join(map(repr, self._context_providers))
        return f"{self.__class__.__name__}({body})"
