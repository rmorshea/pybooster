from __future__ import annotations

from functools import wraps
from inspect import isasyncgenfunction, iscoroutinefunction, isfunction, isgeneratorfunction
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Mapping,
    NewType,
    ParamSpec,
    TypeVar,
    cast,
    overload,
)

from ninject._private import (
    INJECTED,
    ContainerInfo,
    ProviderInfo,
    SyncProviderInfo,
    UniformContext,
    UniformContextProvider,
    add_dependency,
    async_exhaust_exits,
    exhaust_exits,
    get_caller_module_name,
    get_context_provider,
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
        new_type.__module__ = get_caller_module_name()
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
    def provides(self, provider: AnyProvider[R], /) -> AnyProvider[R]: ...

    @overload
    def provides(
        self,
        provider: AnyProvider[R] | None = ...,
        *,
        cls: type[R],
    ) -> Callable[[AnyProvider[R]], AnyProvider[R]]: ...

    def provides(
        self,
        provider: AnyProvider[R] | None = None,
        cls: type[R] | None = None,
    ) -> AnyProvider[R] | Callable[[AnyProvider[R]], AnyProvider[R]]:
        """Add a provider function."""

        def decorator(provider: AnyProvider[R]) -> AnyProvider[R]:
            provider_info = get_provider_info(provider, cls)

            if not provider_info.container_info:
                self._provides_one(provider_info)
            else:
                add_dependency(provider_info.type)
                self._provides_one(provider_info)
                self._provides_many(provider_info.container_info, is_sync=isinstance(provider_info, SyncProviderInfo))

            return provider

        return decorator if provider is None else decorator(provider)

    def _provides_one(self, info: ProviderInfo[Any]) -> None:
        if info.type in self._context_providers:
            msg = f"Provider for {info.type} has already been set"
            raise RuntimeError(msg)
        self._context_providers[info.type] = _make_context_provider(info)

    def _provides_many(self, container_info: ContainerInfo, *, is_sync: bool) -> None:
        from_obj = container_info.kind == "obj"
        for dep_key, dep_type in container_info.dependencies.items():
            item_provider = _make_item_provider(dep_key, is_sync=is_sync, from_obj=from_obj)
            provide_item = _make_injection_wrapper(item_provider, {"value": dep_type})
            self.provides(provide_item, cls=dep_type)

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


def _make_context_provider(info: ProviderInfo[R]) -> UniformContextProvider[R]:
    var = setdefault_context_var(info.type)
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
                    kwargs[name] = await context.__aenter__()  # noqa: PLC2801
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
                    kwargs[name] = context.__enter__()  # noqa: PLC2801
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
                    kwargs[name] = await context.__aenter__()  # noqa: PLC2801
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
                    kwargs[name] = context.__enter__()  # noqa: PLC2801
                    contexts.append(context)
                return func(*args, **kwargs)
            finally:
                exhaust_exits(contexts)

        wrapper = sync_wrapper

    else:
        msg = f"Unsupported function type: {func}"
        raise TypeError(msg)

    return cast(Callable[P, R], wraps(cast(Callable, func))(wrapper))


def _make_item_provider(item: Any, *, is_sync: bool, from_obj: bool) -> SyncFunctionProvider | AsyncFunctionProvider:
    if from_obj:
        if not isinstance(item, str):  # nocov
            msg = f"Expected field to be a string, got {item}"
            raise TypeError(msg)

        if is_sync:

            def sync_provide_attr_field(*, value: Any = inject.ed) -> Any:
                return getattr(value, item)

            return sync_provide_attr_field

        else:

            async def async_provide_attr_field(*, value: Any = inject.ed) -> Any:  # noqa: RUF029
                return getattr(value, item)

            return async_provide_attr_field

    elif is_sync:

        def sync_provide_item_field(*, value: Any = inject.ed) -> Any:
            return value[item]

        return sync_provide_item_field

    else:

        async def async_provide_item_field(*, value: Any = inject.ed) -> Any:  # noqa: RUF029
            return value[item]

        return async_provide_item_field


class InvalidDependencyError(TypeError):
    """Raised when a dependency is invalid."""
