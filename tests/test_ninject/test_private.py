from contextlib import asynccontextmanager, contextmanager
from functools import wraps
from typing import AsyncIterator, Callable, ContextManager, Generator, Iterator

import pytest

from ninject._private import (
    INJECTED,
    _get_wrapped,
    async_exhaust_exits,
    exhaust_exits,
    get_context_provider,
    get_injected_dependency_types_from_callable,
    get_provider_info,
)


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
    def func_1(*, _a: int = INJECTED, _b: str = INJECTED):
        raise NotImplementedError()

    assert get_injected_dependency_types_from_callable(func_1) == {"_a": int, "_b": str}

    def func_2(*, _a: "int" = INJECTED, _b: "str" = INJECTED):
        raise NotImplementedError()

    assert get_injected_dependency_types_from_callable(func_2) == {"_a": int, "_b": str}


def test_get_injected_context_vars_from_callable_error_if_locals_when_annotation_is_str():
    class Thing:
        ...

    def func(*, _a: "Thing" = INJECTED):
        raise NotImplementedError()

    with pytest.raises(NameError, match=r"name .* is not defined - is it defined as a global"):
        get_injected_dependency_types_from_callable(func)


def test_injected_parameter_must_be_keyword_only():
    def func(_a: int = INJECTED):
        raise NotImplementedError()

    with pytest.raises(TypeError, match="Expected injected parameter .* to be keyword-only"):
        get_injected_dependency_types_from_callable(func)


def test_get_wrapped():
    def func():
        raise NotImplementedError()

    @wraps(func)
    def wrapper():
        raise NotImplementedError()

    assert _get_wrapped(func) == func


def test_get_context_provider_error_if_missing():
    class Thing:
        ...

    with pytest.raises(RuntimeError, match="No provider declared for"):
        get_context_provider(Thing)


PROVIDER_AND_EXPECTED_TYPE = []


def add_provider_and_expected_type(cls: type) -> Callable[[Callable], Callable]:
    def decorator(func) -> Callable:
        PROVIDER_AND_EXPECTED_TYPE.append((func, cls))
        return func

    return decorator


@add_provider_and_expected_type(int)
def sync_func() -> int:
    ...


@add_provider_and_expected_type(int)
def sync_iter() -> Iterator[int]:
    ...


@add_provider_and_expected_type(int)
def sync_gen() -> Generator[int, None, None]:
    ...


@add_provider_and_expected_type(int)
class SyncContextManagerTypeInGeneric(ContextManager[int]):
    ...


@add_provider_and_expected_type(int)
class SyncContextManagerTypeInEnter(ContextManager):
    def __enter__(self) -> int:
        ...


@add_provider_and_expected_type(int)
async def async_func() -> int:
    ...


@add_provider_and_expected_type(int)
async def async_iter() -> AsyncIterator[int]:
    ...


@pytest.mark.parametrize("provider, expected_type", PROVIDER_AND_EXPECTED_TYPE)
def test_get_provider_info_provides_type(provider, expected_type):
    assert get_provider_info(provider).provides_type == expected_type
