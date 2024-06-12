from typing import Annotated, TypedDict

import pytest

from ninject import Context, Dependency, inject
from ninject.types import dependencies

MyInt = Dependency[int, "my_int"]
MyStr = Dependency[str, "my_str"]
MyBytes = Dependency[bytes, "my_bytes"]


def test_inject_repr():
    assert repr(inject) == "inject()"


def test_injected_repr():
    assert repr(inject.ed) == "INJECTED"


def test_inject_single_dependency_from_sync_function_provider():
    context = Context()

    @context.provides(MyInt)
    def provide_my_int():
        return 42

    @inject
    def use_my_int(*, my_str: MyInt = inject.ed):
        return my_str

    with context:
        assert use_my_int() == 42


async def test_inject_single_dependency_from_async_function_provider():
    context = Context()

    @context.provides(MyInt)
    async def provide_my_int():
        return 42

    @inject
    async def use_my_int(*, my_str: MyInt = inject.ed):
        return my_str

    with context:
        assert await use_my_int() == 42


def test_inject_single_dependency_from_sync_generator_provider():
    context = Context()

    did_cleanup = False

    @context.provides(MyInt)
    def provide_my_int():
        try:
            yield 42
        finally:
            nonlocal did_cleanup
            did_cleanup = True

    @inject
    def use_my_int(*, my_str: MyInt = inject.ed):
        return my_str

    with context:
        assert not did_cleanup
        assert use_my_int() == 42
        assert did_cleanup


async def test_inject_single_dependency_from_async_generator_provider():
    context = Context()

    did_cleanup = False

    @context.provides(MyInt)
    async def provide_my_int():
        try:
            yield 42
        finally:
            nonlocal did_cleanup
            did_cleanup = True

    @inject
    async def use_my_int(*, my_str: MyInt = inject.ed):
        return my_str

    with context:
        assert not did_cleanup
        assert await use_my_int() == 42
        assert did_cleanup


def test_inject_single_dependency_from_sync_context_manager_provider():
    context = Context()

    did_cleanup = False

    @context.provides(MyInt)
    class MyIntProvider:
        def __enter__(self):
            return 42

        def __exit__(self, etype, evalue, etrace):
            nonlocal did_cleanup
            did_cleanup = True

    @inject
    def use_my_int(*, my_str: MyInt = inject.ed):
        return my_str

    with context:
        assert not did_cleanup
        assert use_my_int() == 42
        assert did_cleanup


async def test_inject_single_dependency_from_async_context_manager_provider():
    context = Context()

    did_cleanup = False

    @context.provides(MyInt)
    class MyIntProvider:
        async def __aenter__(self):
            return 42

        async def __aexit__(self, etype, evalue, etrace):
            nonlocal did_cleanup
            did_cleanup = True

    @inject
    async def use_my_int(*, my_str: MyInt = inject.ed):
        return my_str

    with context:
        assert not did_cleanup
        assert await use_my_int() == 42
        assert did_cleanup


def test_nesting_providers_contexts():
    context_1 = Context()
    context_2 = Context()

    @context_1.provides(MyInt)
    def provide_my_first_int():
        return 42

    @context_2.provides(MyInt)
    def provide_my_second_int():
        return 123

    @inject
    def use_my_int(*, my_str: MyInt = inject.ed):
        return my_str

    with context_1:
        assert use_my_int() == 42
        with context_2:
            assert use_my_int() == 123
        assert use_my_int() == 42


def test_sync_provider_with_sync_dependency():
    context = Context()

    @context.provides(MyInt)
    def provide_my_int():
        return 42

    @context.provides(MyStr)
    def provide_my_str(*, my_int: MyInt = inject.ed):
        return f"The answer is... {my_int}"

    @inject
    def use_my_str(*, my_str: MyStr = inject.ed):
        return my_str

    with context:
        assert use_my_str() == "The answer is... 42"


async def test_sync_provider_with_async_dependency_used_in_async_function():
    context = Context()

    @context.provides(MyInt)
    async def provide_my_int():
        return 42

    @context.provides(MyStr)
    def provide_my_str(*, my_int: MyInt = inject.ed):
        return f"The answer is... {my_int}"

    @inject
    async def use_my_str(*, my_str: MyStr = inject.ed):
        return my_str

    with context:
        assert await use_my_str() == "The answer is... 42"


def test_sync_provider_with_async_dependency_used_in_sync_function():
    context = Context()

    @context.provides(MyInt)
    async def provide_my_int():
        raise NotImplementedError()

    @context.provides(MyStr)
    def provide_my_str(*, _: MyInt = inject.ed):
        raise NotImplementedError()

    @inject
    def use_my_str(*, _: MyStr = inject.ed):
        raise NotImplementedError()

    with context:
        with pytest.raises(RuntimeError):
            use_my_str()


async def test_async_provider_with_sync_dependency_used_in_async_function():
    context = Context()

    @context.provides(MyInt)
    def provide_my_int():
        return 42

    @context.provides(MyStr)
    async def provide_my_str(*, my_int: MyInt = inject.ed):
        return f"The answer is... {my_int}"

    @inject
    async def use_my_str(*, my_str: MyStr = inject.ed):
        return my_str

    with context:
        assert await use_my_str() == "The answer is... 42"


def test_provides_typed_dict():
    context = Context()

    @dependencies
    class IntAndStr(TypedDict):
        int: MyInt
        str: MyStr
        something_else: list[str]

    @context.provides(IntAndStr)
    def provide_my_dict():
        return {"int": 42, "str": "Hello", "something_else": ["a", "b"]}

    @inject
    def use_my_dict(*, my_str: MyStr = inject.ed, my_int: MyInt = inject.ed, my_dict: IntAndStr = inject.ed):
        assert my_str == my_dict["str"]
        assert my_int == my_dict["int"]
        return f"{my_str} {my_int} {my_dict['something_else']}"

    with context:
        assert use_my_dict() == "Hello 42 ['a', 'b']"


def test_reuse_sync_provider():
    context = Context()

    @context.provides(MyInt)
    def provide_my_int():
        return 42

    @inject
    def use_my_int_1(*, my_str: MyInt = inject.ed):
        return my_str

    @inject
    def use_my_int_2(*, my_str: MyInt = inject.ed):
        return my_str + use_my_int_1()

    with context:
        assert use_my_int_2() == 84
        assert use_my_int_1() == 42


async def test_reuse_async_provider():
    context = Context()

    @context.provides(MyInt)
    async def provide_my_int():
        return 42

    @inject
    async def use_my_int_1(*, my_str: MyInt = inject.ed):
        return my_str

    @inject
    async def use_my_int_2(*, my_str: MyInt = inject.ed):
        return my_str + await use_my_int_1()

    with context:
        assert await use_my_int_2() == 84
        assert await use_my_int_1() == 42


def test_error_if_register_provider_for_same_dependency():
    context = Context()

    @context.provides(MyInt)
    def provide_my_int():
        raise NotImplementedError()

    with pytest.raises(RuntimeError):

        @context.provides(MyInt)
        def provide_my_int_again():  # nocov
            raise NotImplementedError()


def test_annotation_for_provides_must_have_context_var():
    context = Context()

    with pytest.raises(TypeError, match=r"Expected .* to be annotated with a context var"):

        @context.provides(Annotated[int, "not var"])
        def provide_my_int():  # nocov
            raise NotImplementedError()


def test_annotation_for_typeddict_provides_must_have_context_var():
    context = Context()

    with pytest.raises(TypeError, match=r"Expected .* to be annotated with a context var"):

        @context.provides(TypedDict("MyDict", {"int": Annotated[int, "not var"]}))
        def provide_my_dict():  # nocov
            raise NotImplementedError()


def test_unsupported_provider_type():

    context = Context()

    with pytest.raises(TypeError, match="Unsupported provider type"):

        @context.provides(MyInt)
        class NotContextManager:
            pass

    class NotValidProvider:
        def __call__(self):
            raise NotImplementedError()

    with pytest.raises(TypeError, match="Unsupported provider type"):

        context.provides(MyInt)(NotValidProvider())


def test_provider_not_called_if_dependency_provided_explicitely():
    context = Context()

    @context.provides(MyInt)
    def provide_my_int():
        raise NotImplementedError()

    @inject
    def use_my_int(*, my_int: MyInt = inject.ed):
        return my_int

    with context:
        assert use_my_int(my_int=123) == 123


async def test_inject_handles_exits_if_error_in_provider_for_each_injected_function_type():
    context = Context()
    exit_called = False
    expected_error_message = "An expected error"

    @context.provides(MyInt)
    def provide_my_int():
        try:
            yield 42
        finally:
            nonlocal exit_called
            exit_called = True

    @inject
    def use_my_int_and_str(*, _: MyInt = inject.ed):
        raise RuntimeError(expected_error_message)

    with pytest.raises(RuntimeError, match=expected_error_message):
        with context:
            use_my_int_and_str()

    assert exit_called
    exit_called = False

    @inject
    async def use_my_int_and_str(*, _: MyInt = inject.ed):
        raise RuntimeError(expected_error_message)

    with pytest.raises(RuntimeError, match=expected_error_message):
        with context:
            await use_my_int_and_str()

    assert exit_called
    exit_called = False

    @inject
    def use_my_int_and_str(*, _: MyInt = inject.ed):
        yield
        raise RuntimeError(expected_error_message)

    with pytest.raises(RuntimeError, match=expected_error_message):
        with context:
            list(use_my_int_and_str())

    assert exit_called
    exit_called = False

    @inject
    async def use_my_int_and_str(*, _: MyInt = inject.ed):
        yield
        raise RuntimeError(expected_error_message)

    with pytest.raises(RuntimeError, match=expected_error_message):
        with context:
            async for _ in use_my_int_and_str():
                pass

    assert exit_called
    exit_called = False


def test_unsupported_function_type_for_injected():
    class UnsupportedFunction:
        def __call__(self):
            raise NotImplementedError()

    with pytest.raises(TypeError, match="Unsupported function type"):
        inject(UnsupportedFunction())
