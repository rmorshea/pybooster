from collections.abc import AsyncGenerator
from collections.abc import AsyncIterator
from collections.abc import Generator
from collections.abc import Iterator
from contextlib import AbstractAsyncContextManager
from contextlib import AbstractContextManager
from contextlib import asynccontextmanager
from contextlib import contextmanager
from functools import wraps
from typing import Callable
from typing import Literal
from typing import NewType

import pytest

from ninject._private.inspect import INJECTED
from ninject._private.inspect import AsyncScopeParams
from ninject._private.inspect import ScopeParams
from ninject._private.inspect import SyncScopeParams
from ninject._private.inspect import get_dependency_types_from_callable
from ninject._private.inspect import get_scope_params
from ninject._private.inspect import get_wrapped
from ninject._private.scope import get_scope_provider
from ninject._private.scope import make_scope_providers
from ninject._private.utils import async_exhaust_exits
from ninject._private.utils import exhaust_exits


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

    assert get_dependency_types_from_callable(func_1) == {"_a": int, "_b": str}

    def func_2(*, _a: "int" = INJECTED, _b: "str" = INJECTED): ...

    assert get_dependency_types_from_callable(func_2) == {"_a": int, "_b": str}


def test_get_injected_context_vars_from_callable_error_if_locals_when_annotation_is_str():
    class Thing: ...

    def func(*, _a: "Thing" = INJECTED): ...

    with pytest.raises(NameError, match=r"name .* is not defined - is it defined as a global"):
        get_dependency_types_from_callable(func)


def test_injected_parameter_must_be_keyword_only():
    def func(_a: int = INJECTED): ...

    with pytest.raises(TypeError, match="Expected injected parameter .* to be keyword-only"):
        get_dependency_types_from_callable(func)


def test_get_wrapped():
    def func(): ...

    @wraps(func)
    def wrapper(): ...

    assert get_wrapped(func) == func


def test_get_context_provider_error_if_missing():
    class Thing: ...

    with pytest.raises(RuntimeError, match="No provider declared for"):
        get_scope_provider(Thing)


PROVIDER_AND_EXPECTED_TYPE: list[tuple[ScopeParams, type, Literal["sync", "async"]]] = []


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
    params = get_scope_params(provider)
    assert params.provided_type == expected_type
    if sync_or_async == "sync":
        assert isinstance(params, SyncScopeParams)
    else:
        assert isinstance(params, AsyncScopeParams)


def test_provider_info_tuple_container_info():
    nt1 = NewType("nt1", int)
    nt2 = NewType("nt2", int)

    def fake_provider() -> tuple[nt1, nt2]: ...

    actual_types = set(make_scope_providers(get_scope_params(fake_provider), {}))
    assert actual_types == {tuple[nt1, nt2], nt1, nt2}


def test_provided_type_must_be_context_manager_if_not_callable():
    class NotContextManager: ...

    with pytest.raises(TypeError, match="Unsupported provider type"):
        get_scope_params(NotContextManager)


def test_explicit_type_must_be_context_manager_if_not_callable():
    class NotContextManager: ...

    with pytest.raises(TypeError, match="Unsupported provider type"):
        get_scope_params(NotContextManager, int)
