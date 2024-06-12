from contextvars import ContextVar
from typing import Annotated, TypedDict

import pytest

from ninject import Providers, inject

MyInt = Annotated[int, ContextVar("my_int")]
MyStr = Annotated[str, ContextVar("my_str")]
MyBytes = Annotated[bytes, ContextVar("my_bytes")]


def test_inject_repr():
    assert repr(inject) == "inject()"


def test_injected_repr():
    assert repr(inject.ed) == "INJECTED"


def test_inject_single_dependency_from_sync_function_provider():
    context = Providers()

    @context.provides(MyInt)
    def provide_my_int():
        return 42

    @inject
    def use_my_int(my_str: MyInt = inject.ed):
        return my_str

    with context:
        assert use_my_int() == 42


async def test_inject_single_dependency_from_async_function_provider():
    context = Providers()

    @context.provides(MyInt)
    async def provide_my_int():
        return 42

    @inject
    async def use_my_int(my_str: MyInt = inject.ed):
        return my_str

    with context:
        assert await use_my_int() == 42


def test_inject_single_dependency_from_sync_generator_provider():
    context = Providers()

    did_cleanup = False

    @context.provides(MyInt)
    def provide_my_int():
        try:
            yield 42
        finally:
            nonlocal did_cleanup
            did_cleanup = True

    @inject
    def use_my_int(my_str: MyInt = inject.ed):
        return my_str

    with context:
        assert not did_cleanup
        assert use_my_int() == 42
        assert did_cleanup


async def test_inject_single_dependency_from_async_generator_provider():
    context = Providers()

    did_cleanup = False

    @context.provides(MyInt)
    async def provide_my_int():
        try:
            yield 42
        finally:
            nonlocal did_cleanup
            did_cleanup = True

    @inject
    async def use_my_int(my_str: MyInt = inject.ed):
        return my_str

    with context:
        assert not did_cleanup
        assert await use_my_int() == 42
        assert did_cleanup


def test_inject_single_dependency_from_sync_context_manager_provider():
    context = Providers()

    did_cleanup = False

    @context.provides(MyInt)
    class MyIntProvider:
        def __enter__(self):
            return 42

        def __exit__(self, etype, evalue, etrace):
            nonlocal did_cleanup
            did_cleanup = True

    @inject
    def use_my_int(my_str: MyInt = inject.ed):
        return my_str

    with context:
        assert not did_cleanup
        assert use_my_int() == 42
        assert did_cleanup


async def test_inject_single_dependency_from_async_context_manager_provider():
    context = Providers()

    did_cleanup = False

    @context.provides(MyInt)
    class MyIntProvider:
        async def __aenter__(self):
            return 42

        async def __aexit__(self, etype, evalue, etrace):
            nonlocal did_cleanup
            did_cleanup = True

    @inject
    async def use_my_int(my_str: MyInt = inject.ed):
        return my_str

    with context:
        assert not did_cleanup
        assert await use_my_int() == 42
        assert did_cleanup


def test_nesting_providers_contexts():
    context_1 = Providers()
    context_2 = Providers()

    @context_1.provides(MyInt)
    def provide_my_first_int():
        return 42

    @context_2.provides(MyInt)
    def provide_my_second_int():
        return 123

    @inject
    def use_my_int(my_str: MyInt = inject.ed):
        return my_str

    with context_1:
        assert use_my_int() == 42
        with context_2:
            assert use_my_int() == 123
        assert use_my_int() == 42


def test_sync_provider_with_sync_dependency():
    context = Providers()

    @context.provides(MyInt)
    def provide_my_int():
        return 42

    @context.provides(MyStr)
    def provide_my_str(my_int: MyInt = inject.ed):
        return f"The answer is... {my_int}"

    @inject
    def use_my_str(my_str: MyStr = inject.ed):
        return my_str

    with context:
        assert use_my_str() == "The answer is... 42"


async def test_sync_provider_with_async_dependency_used_in_async_function():
    context = Providers()

    @context.provides(MyInt)
    async def provide_my_int():
        return 42

    @context.provides(MyStr)
    def provide_my_str(my_int: MyInt = inject.ed):
        return f"The answer is... {my_int}"

    @inject
    async def use_my_str(my_str: MyStr = inject.ed):
        return my_str

    with context:
        assert await use_my_str() == "The answer is... 42"


def test_sync_provider_with_async_dependency_used_in_sync_function():
    context = Providers()

    @context.provides(MyInt)
    async def provide_my_int():
        raise NotImplementedError()

    @context.provides(MyStr)
    def provide_my_str(_: MyInt = inject.ed):
        raise NotImplementedError()

    @inject
    def use_my_str(_: MyStr = inject.ed):
        raise NotImplementedError()

    with context:
        with pytest.raises(RuntimeError):
            use_my_str()


async def test_async_provider_with_sync_dependency_used_in_async_function():
    context = Providers()

    @context.provides(MyInt)
    def provide_my_int():
        return 42

    @context.provides(MyStr)
    async def provide_my_str(my_int: MyInt = inject.ed):
        return f"The answer is... {my_int}"

    @inject
    async def use_my_str(my_str: MyStr = inject.ed):
        return my_str

    with context:
        assert await use_my_str() == "The answer is... 42"


def test_provides_typed_dict():
    context = Providers()

    @context.provides(TypedDict("MyDict", {"int": MyInt, "str": MyStr}))
    def provide_my_dict():
        return {"int": 42, "str": "Hello"}

    @inject
    def use_my_str(my_str: MyStr = inject.ed, my_int: MyInt = inject.ed):
        return f"{my_str} {my_int}"

    with context:
        assert use_my_str() == "Hello 42"
