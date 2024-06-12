from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar
from functools import wraps
from typing import Annotated, get_type_hints

import pytest

from ninject._private import (
    INJECTED,
    async_exhaust_exits,
    exhaust_exits,
    get_context_provider,
    get_context_var_from_annotation,
    get_injected_context_vars_from_callable,
    get_wrapped,
)

VAR_A = ContextVar("a")
VAR_B = ContextVar("b")


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


def test_get_context_var_from_annotation():
    assert get_context_var_from_annotation(int) is None

    var = ContextVar("name")
    assert get_context_var_from_annotation(Annotated[int, var]) is var

    with pytest.raises(TypeError, match="Expected exactly one ContextVar"):
        get_context_var_from_annotation(Annotated[int, var, var])


def test_get_injected_context_vars_from_callable():

    def func(*, _a: Annotated[int, VAR_A] = INJECTED, _b: Annotated[str, VAR_B] = INJECTED):
        raise NotImplementedError()

    assert get_injected_context_vars_from_callable(func) == {"_a": VAR_A, "_b": VAR_B}

    def func(*, _a: "Annotated[int, VAR_A]" = INJECTED, _b: "Annotated[str, VAR_B]" = INJECTED):
        raise NotImplementedError()

    assert get_injected_context_vars_from_callable(func) == {"_a": VAR_A, "_b": VAR_B}

    def func(_a: Annotated[int, "not var"], _b: Annotated[str, "not var"] = "default"):
        raise NotImplementedError()

    assert get_injected_context_vars_from_callable(func) == {}


def test_get_injected_context_vars_from_callable_error_if_injected_default_by_no_var():
    def func(*, _a: Annotated[int, "no var"] = INJECTED):
        raise NotImplementedError()

    with pytest.raises(TypeError, match=r"Expected .* to be annotated with a "):
        get_injected_context_vars_from_callable(func)

    def func(*, _a: int = INJECTED):
        raise NotImplementedError()

    with pytest.raises(TypeError, match=r"Expected .* to be annotated with a "):
        get_injected_context_vars_from_callable(func)


def test_get_injected_context_vars_from_callable_error_if_locals_when_annotation_is_str():
    var_a = ContextVar("a")

    def func(*, a: "Annotated[int, var_a]" = INJECTED):
        raise NotImplementedError()

    with pytest.raises(NameError, match=r"name .* is not defined - is it defined as a global"):
        get_injected_context_vars_from_callable(func)


def test_injected_parameter_must_be_keyword_only():
    def func(_a: Annotated[int, VAR_A] = INJECTED):
        raise NotImplementedError()

    with pytest.raises(TypeError, match="Expected injected parameter .* to be keyword-only"):
        get_injected_context_vars_from_callable(func)


def test_get_wrapped():
    def func():
        raise NotImplementedError()

    @wraps(func)
    def wrapper():
        raise NotImplementedError()

    assert get_wrapped(func) == func


def test_get_context_provider():
    var = ContextVar("name")

    with pytest.raises(RuntimeError, match="No provider declared for"):
        get_context_provider(var)
