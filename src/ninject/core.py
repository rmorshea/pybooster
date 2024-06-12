from __future__ import annotations

from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar
from functools import wraps
from inspect import (
    isasyncgenfunction,
    iscoroutinefunction,
    isfunction,
    isgeneratorfunction,
)
from typing import (
    Any,
    AsyncContextManager,
    Callable,
    ContextManager,
    Mapping,
    ParamSpec,
    TypedDict,
    TypeVar,
    cast,
    get_args,
    get_type_hints,
)

from ninject._private import (
    INJECTED,
    AsyncUniformContext,
    SyncUniformContext,
    UniformContext,
    UniformContextProvider,
    async_exhaust_exits,
    asyncfunctioncontextmanager,
    exhaust_exits,
    get_context_provider,
    get_context_var_from_annotation,
    get_injected_context_vars_from_callable,
    get_wrapped,
    set_context_provider,
    syncfunctioncontextmanager,
)
from ninject.types import AnyProvider

P = ParamSpec("P")
R = TypeVar("R")


class Inject:
    """A decorator to inject values into a function."""

    ed = INJECTED
    """A sentinel value to indicate that a parameter should be injected."""

    def __call__(self, func: Callable[P, R]) -> Callable[P, R]:
        """Inject values into a function."""
        dependencies = get_injected_context_vars_from_callable(func)
        return _make_injection_wrapper(func, dependencies)

    def __repr__(self) -> str:
        return "inject()"


inject = Inject()
"""A decorator to inject values into a function."""
del Inject


class Context:
    """A context manager for setting provider functions."""

    def __init__(self) -> None:
        self._context_providers: dict[ContextVar, UniformContextProvider] = {}

    def provides(self, annotation: type[R]) -> Callable[[AnyProvider[R]], AnyProvider[R]]:
        """Add a provider function."""
        if not (var := get_context_var_from_annotation(annotation)):
            msg = f"Expected {annotation!r} to be annotated with a context var"
            raise TypeError(msg)

        annotation_type = get_args(annotation)[0]
        if issubclass(annotation_type, dict) and TypedDict in getattr(annotation_type, "__orig_bases__", ()):
            return self._provides_dict(var, annotation_type)
        else:
            return self._provides_scalar(var)

    def _provides_scalar(self, var: ContextVar[R]) -> Callable[[AnyProvider[R]], AnyProvider[R]]:
        def decorator(provider: AnyProvider[R]) -> AnyProvider[R]:
            if var in self._context_providers:
                msg = f"Provider for {var} has already been set"
                raise RuntimeError(msg)
            self._context_providers[var] = _make_context_provider(var, provider)
            return provider

        return decorator

    def _provides_dict(self, var: ContextVar[R], cls: type[R]) -> Callable[[AnyProvider[R]], AnyProvider[R]]:
        def decorator(provider: AnyProvider[R]) -> AnyProvider[R]:
            self._context_providers[var] = _make_context_provider(var, provider)

            for field_name, field_type in get_type_hints(cls, include_extras=True).items():
                if field_var := get_context_var_from_annotation(field_type):
                    provide_field = _make_injection_wrapper(
                        lambda field_name=field_name, *, provided_dict: provided_dict[field_name],
                        {"provided_dict": var},
                    )
                    self._context_providers[field_var] = _make_context_provider(field_var, provide_field)

            return provider

        return decorator

    def __enter__(self) -> None:
        self._reset_callbacks = [set_context_provider(v, p) for v, p in self._context_providers.items()]

    def __exit__(self, etype: Any, evalue: Any, atrace: Any, /) -> None:
        try:
            for reset in self._reset_callbacks:
                reset()
        finally:
            del self._reset_callbacks


def _make_context_provider(
    var: ContextVar[R],
    provider: AnyProvider[R],
) -> UniformContextProvider[R]:
    wrapped = get_wrapped(provider)
    dependencies = tuple(get_injected_context_vars_from_callable(wrapped).values())

    if isinstance(wrapped := get_wrapped(provider), type):
        if issubclass(wrapped, ContextManager):
            return lambda: SyncUniformContext(var, provider, dependencies)
        elif issubclass(wrapped, AsyncContextManager):
            return lambda: AsyncUniformContext(var, provider, dependencies)
    elif isasyncgenfunction(provider):
        ctx_provider = asynccontextmanager(inject(provider))
        return lambda: AsyncUniformContext(var, ctx_provider, dependencies)
    elif iscoroutinefunction(provider):
        ctx_provider = asyncfunctioncontextmanager(inject(provider))
        return lambda: AsyncUniformContext(var, ctx_provider, dependencies)
    elif isgeneratorfunction(provider):
        ctx_provider = contextmanager(inject(provider))
        return lambda: SyncUniformContext(var, ctx_provider, dependencies)
    elif isfunction(provider):
        ctx_provider = syncfunctioncontextmanager(inject(provider))
        return lambda: SyncUniformContext(var, ctx_provider, dependencies)

    msg = f"Unsupported provider type: {provider} - expected one of: {AnyProvider}"
    raise TypeError(msg)


def _make_injection_wrapper(
    func: Callable[P, R],
    dependencies: Mapping[str, ContextVar],
) -> Callable[P, R]:

    wrapper: Callable[..., Any]
    if isasyncgenfunction(func):

        async def async_gen_wrapper(*args: Any, **kwargs: Any) -> Any:
            contexts: list[UniformContext] = []

            try:
                for name in dependencies.keys() - kwargs.keys():
                    var = dependencies[name]
                    context = get_context_provider(var)()
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
                    var = dependencies[name]
                    context = get_context_provider(var)()
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
                    var = dependencies[name]
                    context = get_context_provider(var)()
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
                    var = dependencies[name]
                    context = get_context_provider(var)()
                    kwargs[name] = context.__enter__()
                    contexts.append(context)
                return func(*args, **kwargs)
            finally:
                exhaust_exits(contexts)

        wrapper = sync_wrapper

    else:
        msg = f"Unsupported function type: {func}"
        raise TypeError(msg)

    return cast(Callable[P, R], wraps(func)(wrapper))
