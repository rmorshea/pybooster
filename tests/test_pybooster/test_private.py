from contextlib import asynccontextmanager
from contextlib import contextmanager

import pytest
from anyio import create_task_group

from pybooster import injector
from pybooster import required
from pybooster._private._provider import get_provides_type
from pybooster._private._utils import AsyncFastStack
from pybooster._private._utils import FastStack
from pybooster._private._utils import get_required_parameters
from pybooster._private._utils import start_future


async def test_start_future_raises_if_called_early():
    async def example(): ...

    async with create_task_group() as tg:
        future = start_future(tg, example())
        with pytest.raises(RuntimeError):
            future()


def test_required_parameter_must_be_kw_only():
    with pytest.raises(TypeError, match=r"Expected dependant parameter .* to be keyword-only."):

        @injector.function
        def func(_: int = required):  # nocov
            raise AssertionError


def test_fast_stack_callback():
    stack = FastStack()

    called = False

    @stack.push_callback
    def callback():
        nonlocal called
        called = True

    stack.close()
    assert called


def test_fast_stack_push_context_manager():
    stack = FastStack()

    exit_called = False

    @contextmanager
    def context():
        try:
            yield 42
        finally:
            nonlocal exit_called
            exit_called = True

    assert stack.enter_context(context()) == 42
    stack.close()
    assert exit_called


def test_fast_stack_exception_stack_preserved():
    stack = FastStack()

    class CustomError(Exception):
        def __init__(self, value: int = 0):
            self.value = value
            super().__init__(value)

    errors: list[CustomError] = []

    @contextmanager
    def record_and_raise_exception(error):
        try:
            yield
        except CustomError as e:
            errors.append(e)
            raise error from e

    stack.enter_context(record_and_raise_exception(CustomError(1)))
    stack.enter_context(record_and_raise_exception(CustomError(2)))
    stack.enter_context(record_and_raise_exception(CustomError(3)))

    try:
        raise CustomError(4)  # noqa: TRY301
    except CustomError:
        with pytest.raises(CustomError):
            stack.close()

    assert [e.value for e in errors] == [4, 3, 2]  # the last error isn't appended


async def test_async_fast_stack_callback():
    stack = AsyncFastStack()

    called = False

    @stack.push_async_callback
    async def callback():
        nonlocal called
        called = True

    await stack.aclose()
    assert called


async def test_async_fast_stack_push_context_manager():
    stack = AsyncFastStack()

    exit_called = False

    @asynccontextmanager
    async def context():
        try:
            yield 42
        finally:
            nonlocal exit_called
            exit_called = True

    assert await stack.enter_async_context(context()) == 42
    await stack.aclose()
    assert exit_called


async def test_async_fast_stack_exception_stack_preserved():
    stack = AsyncFastStack()

    class CustomError(Exception):
        def __init__(self, value: int = 0):
            self.value = value
            super().__init__(value)

    errors: list[CustomError] = []

    @asynccontextmanager
    async def record_and_raise_exception(error):
        try:
            yield
        except CustomError as e:
            errors.append(e)
            raise error from e

    await stack.enter_async_context(record_and_raise_exception(CustomError(1)))
    await stack.enter_async_context(record_and_raise_exception(CustomError(2)))
    await stack.enter_async_context(record_and_raise_exception(CustomError(3)))

    try:
        raise CustomError(4)  # noqa: TRY301
    except CustomError:
        with pytest.raises(CustomError):
            await stack.aclose()

    assert [e.value for e in errors] == [4, 3, 2]  # the last error isn't appended


def test_get_provides_type_raises_for_invalid_type():
    with pytest.raises(TypeError, match=r"xpected a type, or function to infer one, but got 1."):
        get_provides_type(1)  # type: ignore[reportArgumentType]


def test_get_required_parameters_mismatch_len_of_requires_list():
    def func(*, a: int = required, b: int = required): ...

    with pytest.raises(
        TypeError,
        match=r"Could not match .* dependencies to .* required parameters.",
    ):
        get_required_parameters(func, [int])


def test_get_required_parameters_mismatch_len_of_requires_map():
    def func(*, a: int = required, b: int = required): ...

    with pytest.raises(
        TypeError,
        match=r"Could not match .* dependencies to .* required parameters.",
    ):
        get_required_parameters(func, {"a": int})
