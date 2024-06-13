from __future__ import annotations

from dataclasses import replace
from functools import wraps
from inspect import isasyncgenfunction, iscoroutinefunction, isfunction, isgeneratorfunction
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Literal,
    Mapping,
    NewType,
    ParamSpec,
    TypeVar,
    cast,
    overload,
)

from ninject._private import (
    INJECTED,
    ProviderInfo,
    SyncProviderInfo,
    UniformContext,
    UniformContextProvider,
    add_dependency,
    async_exhaust_exits,
    exhaust_exits,
    get_context_provider,
    get_dependency_type_info,
    get_injected_dependency_types_from_callable,
    get_provider_info,
    set_context_provider,
    setdefault_context_var,
)
from ninject.types import AnyProvider, AsyncFunctionProvider, SyncFunctionProvider

P = ParamSpec("P")
R = TypeVar("R")


if TYPE_CHECKING:
    Dependency = NewType
else:

    def Dependency(name, tp):  # noqa: N802
        new_type = NewType(name, tp)
        add_dependency(new_type)
        return new_type


class Inject:
    """A decorator to inject values into a function."""

    ed = INJECTED
    """A sentinel value to indicate that a parameter should be injected."""

    def __call__(self, func: Callable[P, R]) -> Callable[P, R]:
        """Inject values into a function."""
        dependencies = get_injected_dependency_types_from_callable(func)
        return _make_injection_wrapper(func, dependencies)

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
    def provides(self, provider: AnyProvider[R], /) -> AnyProvider[R]:
        ...

    @overload
    def provides(
        self,
        provider: AnyProvider[R] | None = ...,
        *,
        cls: type[R],
    ) -> Callable[[AnyProvider[R]], AnyProvider[R]]:
        ...

    def provides(
        self,
        provider: AnyProvider[R] | None = None,
        cls: type[R] | None = None,
    ) -> AnyProvider[R] | Callable[[AnyProvider[R]], AnyProvider[R]]:
        """Add a provider function."""

        def decorator(provider: AnyProvider[R]) -> AnyProvider[R]:
            provider_info = get_provider_info(provider)

            if cls is not None:
                provider_info = replace(provider_info, provides_type=cls)

            attr_or_item, field_types = get_dependency_type_info(provider_info.provides_type)

            if attr_or_item is None:
                self._provides_one(provider_info)
            elif field_types:
                self._provides_many(provider_info, attr_or_item, field_types)
            else:
                msg = (
                    f"Unsupported dependency type {provider_info.provides_type} - "
                    "expected a NewType or a class with NewType fields"
                )
                raise TypeError(msg)

            return provider

        return decorator if provider is None else decorator(provider)

    def _provides_one(self, info: ProviderInfo[Any]) -> None:
        if info.provides_type in self._context_providers:
            msg = f"Provider for {info.provides_type} has already been set"
            raise RuntimeError(msg)
        self._context_providers[info.provides_type] = _make_context_provider(info)

    def _provides_many(
        self,
        info: ProviderInfo[tuple],
        attr_or_item: Literal["attr", "item"],
        field_types: dict[str | int, Any],
    ) -> None:
        add_dependency(info.provides_type)
        self._context_providers[info.provides_type] = _make_context_provider(info)
        for f, f_type in field_types.items():
            provide_item = _make_injection_wrapper(_make_item_provider(info, attr_or_item, f), {"value": f_type})
            self.provides(provide_item, cls=f_type)

    def __enter__(self) -> None:
        self._reset_callbacks = [set_context_provider(v, p) for v, p in self._context_providers.items()]

    def __exit__(self, etype: Any, evalue: Any, atrace: Any, /) -> None:
        try:
            for reset in self._reset_callbacks:
                reset()
        finally:
            del self._reset_callbacks


def _make_context_provider(info: ProviderInfo[R]) -> UniformContextProvider[R]:
    var = setdefault_context_var(info.provides_type)
    context_provider = info.context_provider
    uniform_context_type = info.uniform_context_type
    dependencies = tuple(get_injected_dependency_types_from_callable(info.context_provider).values())
    return lambda: uniform_context_type(var, context_provider, dependencies)  # type: ignore[reportArgumentType]


def _make_injection_wrapper(func: Callable[P, R], dependencies: Mapping[str, type]) -> Callable[P, R]:
    if not dependencies:
        return func

    wrapper: Callable[..., Any]
    if isasyncgenfunction(func):

        async def async_gen_wrapper(*args: Any, **kwargs: Any) -> Any:
            contexts: list[UniformContext] = []

            try:
                for name in dependencies.keys() - kwargs.keys():
                    cls = dependencies[name]
                    context = get_context_provider(cls)()
                    kwargs[name] = await context.__aenter__()
                    contexts.append(context)
                async for value in func(*args, **kwargs):
                    yield value
            finally:
                await async_exhaust_exits(contexts)

        wrapper = async_gen_wrapper

    elif isgeneratorfunction(func):

        def sync_gen_wrapper(*args: Any, **kwargs: Any) -> Any:
            contexts: list[UniformContext] = []
            try:
                for name in dependencies.keys() - kwargs.keys():
                    cls = dependencies[name]
                    context = get_context_provider(cls)()
                    kwargs[name] = context.__enter__()
                    contexts.append(context)
                yield from func(*args, **kwargs)
            finally:
                exhaust_exits(contexts)

        wrapper = sync_gen_wrapper

    elif iscoroutinefunction(func):

        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            contexts: list[UniformContext] = []

            try:
                for name in dependencies.keys() - kwargs.keys():
                    cls = dependencies[name]
                    context = get_context_provider(cls)()
                    kwargs[name] = await context.__aenter__()
                    contexts.append(context)
                return await func(*args, **kwargs)
            finally:
                await async_exhaust_exits(contexts)

        wrapper = async_wrapper

    elif isfunction(func):

        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            contexts: list[UniformContext] = []
            try:
                for name in dependencies.keys() - kwargs.keys():
                    cls = dependencies[name]
                    context = get_context_provider(cls)()
                    kwargs[name] = context.__enter__()
                    contexts.append(context)
                return func(*args, **kwargs)
            finally:
                exhaust_exits(contexts)

        wrapper = sync_wrapper

    else:
        msg = f"Unsupported function type: {func}"
        raise TypeError(msg)

    return cast(Callable[P, R], wraps(cast(Callable, func))(wrapper))


def _make_item_provider(
    info: ProviderInfo,
    attr_or_item: Literal["attr", "item"],
    field: str | int,
) -> SyncFunctionProvider | AsyncFunctionProvider:
    if attr_or_item == "attr":
        if not isinstance(field, str):  # nocov
            msg = f"Expected field to be a string, got {field}"
            raise TypeError(msg)

        if isinstance(info, SyncProviderInfo):

            def sync_provide_attr_field(*, value: Any = inject.ed) -> Any:
                return getattr(value, field)

            return sync_provide_attr_field

        else:

            async def async_provide_attr_field(*, value: Any = inject.ed) -> Any:
                return getattr(value, field)

            return async_provide_attr_field

    elif attr_or_item == "item":
        if isinstance(info, SyncProviderInfo):

            def sync_provide_item_field(*, value: Any = inject.ed) -> Any:
                return value[field]

            return sync_provide_item_field

        else:

            async def async_provide_item_field(*, value: Any = inject.ed) -> Any:
                return value[field]

            return async_provide_item_field


class InvalidDependencyError(TypeError):
    """Raised when a dependency is invalid."""
