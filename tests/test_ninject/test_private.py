from collections.abc import AsyncGenerator, AsyncIterator, Generator, Iterator
from contextlib import AbstractAsyncContextManager, AbstractContextManager, asynccontextmanager, contextmanager
from functools import wraps
from typing import (
    Callable,
    Literal,
    NewType,
    TypedDict,
)

import pytest

from ninject._private import (
    INJECTED,
    AsyncProviderInfo,
    ProviderInfo,
    SyncProviderInfo,
    SyncUniformContext,
    _get_wrapped,
    add_dependency,
    async_exhaust_exits,
    exhaust_exits,
    get_context_provider,
    get_injected_dependency_types_from_callable,
    get_provider_info,
    is_dependency,
    set_context_provider,
)
from ninject.core import Context, Dependency


def test_check_add_and_is_dependency():
    nt = NewType("nt", int)
    add_dependency(nt)
    assert is_dependency(nt)


def test_exhaust_exits():
    exit_calls = []

    @contextmanager
    def cm(value, error_message):
        yield
        exit_calls.append(value)
        raise RuntimeError(error_message)

    cm_1 = cm(1, "error 1")
    cm_2 = cm(2, "error 2")
    cm_3 = cm(3, "error 3")

    cm_1.__enter__()
    cm_2.__enter__()
    cm_3.__enter__()

    with pytest.raises(RuntimeError, match="error 1"):
        exhaust_exits([cm_1, cm_2, cm_3])


async def test_async_exhaust_exits():
    exit_calls = []

    @asynccontextmanager
    async def acm(value, error_message):
        yield
        exit_calls.append(value)
        raise RuntimeError(error_message)

    acm_1 = acm(1, "error 1")
    acm_2 = acm(2, "error 2")
    acm_3 = acm(3, "error 3")

    await acm_1.__aenter__()
    await acm_2.__aenter__()
    await acm_3.__aenter__()

    with pytest.raises(RuntimeError, match="error 1"):
        await async_exhaust_exits([acm_1, acm_2, acm_3])


def test_get_injected_context_vars_from_callable():
    def func_1(*, _a: int = INJECTED, _b: str = INJECTED): ...

    assert get_injected_dependency_types_from_callable(func_1) == {"_a": int, "_b": str}

    def func_2(*, _a: "int" = INJECTED, _b: "str" = INJECTED): ...

    assert get_injected_dependency_types_from_callable(func_2) == {"_a": int, "_b": str}


def test_get_injected_context_vars_from_callable_error_if_locals_when_annotation_is_str():
    class Thing: ...

    def func(*, _a: "Thing" = INJECTED): ...

    with pytest.raises(NameError, match=r"name .* is not defined - is it defined as a global"):
        get_injected_dependency_types_from_callable(func)


def test_injected_parameter_must_be_keyword_only():
    def func(_a: int = INJECTED): ...

    with pytest.raises(TypeError, match="Expected injected parameter .* to be keyword-only"):
        get_injected_dependency_types_from_callable(func)


def test_get_wrapped():
    def func(): ...

    @wraps(func)
    def wrapper(): ...

    assert _get_wrapped(func) == func


def test_get_context_provider_error_if_missing():
    class Thing: ...

    with pytest.raises(RuntimeError, match="No provider declared for"):
        get_context_provider(Thing)


PROVIDER_AND_EXPECTED_TYPE: list[tuple[ProviderInfo, type, Literal["sync", "async"]]] = []


def add_provider_and_expected_type(
    cls: type, sync_or_async: Literal["sync", "async"]
) -> Callable[[Callable], Callable]:
    def decorator(func) -> Callable:
        PROVIDER_AND_EXPECTED_TYPE.append((func, cls, sync_or_async))
        return func

    return decorator


@add_provider_and_expected_type(int, "sync")
def sync_func() -> int: ...


@add_provider_and_expected_type(int, "sync")
def sync_iter() -> Iterator[int]: ...


@add_provider_and_expected_type(int, "sync")
def sync_gen() -> Generator[int, None, None]: ...


@add_provider_and_expected_type(int, "sync")
class SyncContextManager(AbstractContextManager):
    def __enter__(self) -> int: ...


@add_provider_and_expected_type(int, "async")
async def async_func() -> int: ...


@add_provider_and_expected_type(int, "async")
async def async_iter() -> AsyncIterator[int]: ...


@add_provider_and_expected_type(int, "async")
async def async_gen() -> AsyncGenerator[int, None]: ...


@add_provider_and_expected_type(int, "async")
class AsyncContextManager(AbstractAsyncContextManager):
    async def __aenter__(self) -> int: ...


@pytest.mark.parametrize("provider, expected_type, sync_or_async", PROVIDER_AND_EXPECTED_TYPE)
def test_get_provider_info_provides_type(provider, expected_type, sync_or_async):
    info = get_provider_info(provider)
    assert info.type == expected_type
    if sync_or_async == "sync":
        assert isinstance(info, SyncProviderInfo)
    else:
        assert isinstance(info, AsyncProviderInfo)


def test_provider_info_tuple_container_info():
    nt1 = Dependency("nt1", int)
    nt2 = Dependency("nt2", int)

    def fake_provider() -> tuple[nt1, nt2]: ...

    provider_info = get_provider_info(fake_provider)

    assert provider_info.container_info is not None
    assert provider_info.container_info.kind == "map"
    assert provider_info.container_info.dependencies == {0: nt1, 1: nt2}


def test_provider_info_typed_dict_container_info():
    nt1 = Dependency("nt1", int)
    nt2 = Dependency("nt2", int)

    class Thing(TypedDict):
        a: nt1
        b: nt2

    def fake_provider() -> Thing: ...

    provider_info = get_provider_info(fake_provider)

    assert provider_info.container_info is not None
    assert provider_info.container_info.kind == "map"
    assert provider_info.container_info.dependencies == {"a": nt1, "b": nt2}


def test_provider_info_obj_container_info():
    nt1 = Dependency("nt1", int)
    nt2 = Dependency("nt2", int)

    class Thing:
        a: nt1
        b: nt2

    def fake_provider() -> Thing: ...

    provider_info = get_provider_info(fake_provider)

    assert provider_info.container_info is not None
    assert provider_info.container_info.kind == "obj"
    assert provider_info.container_info.dependencies == {"a": nt1, "b": nt2}


def test_cannot_provide_empty_container():
    class Thing: ...

    def fake_provider() -> Thing: ...

    provider_info = get_provider_info(fake_provider)

    with pytest.raises(TypeError, match="must contain at least one dependency"):
        provider_info.container_info  # noqa: B018


def test_uniform_context_repr():
    nt = Dependency("nt", int)

    context = Context()

    @context.provides
    def provider() -> nt: ...

    uniform_context_provider = context._context_providers[nt]

    assert repr(uniform_context_provider()).startswith("SyncUniformContext")


def test_provided_type_must_be_context_manager_if_not_callable():
    class NotContextManager: ...

    with pytest.raises(TypeError, match="Unsupported provider type"):
        get_provider_info(NotContextManager)


def test_explicit_type_must_be_context_manager_if_not_callable():
    class NotContextManager: ...

    with pytest.raises(TypeError, match="Unsupported provider type"):
        get_provider_info(NotContextManager, int)


def test_errors_on_get_context_provider():
    nt = NewType("nt", int)

    def fake_context_provider() -> SyncUniformContext: ...

    with pytest.raises(RuntimeError, match="No provider declared for"):
        get_context_provider(nt)

    reset = set_context_provider(nt, fake_context_provider)
    assert get_context_provider(nt) is fake_context_provider

    reset()
    with pytest.raises(RuntimeError, match="No active provider for"):
        get_context_provider(nt)
