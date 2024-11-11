from __future__ import annotations

from collections.abc import Callable  # noqa: TCH003
from typing import Any
from typing import NewType
from typing import TypeVar

import pytest

from pybooster import injector
from pybooster import provider
from pybooster import required
from pybooster import solution
from pybooster.types import SolutionError

T = TypeVar("T")

Greeting = NewType("Greeting", str)
Recipient = NewType("Recipient", str)
Message = NewType("Message", str)
SideEffect = NewType("SideEffect", None)


def test_sync_injection():

    @provider.function
    def provide_greeting() -> Greeting:
        return Greeting("Hello")

    @provider.function
    def provide_recipient() -> Recipient:
        return Recipient("World")

    @provider.function
    def provide_message(*, greeting: Greeting = required, recipient: Recipient = required) -> Message:
        return Message(f"{greeting} {recipient}")

    @injector.function
    def use_message(*, message: Message = required):
        return message

    with solution(provide_greeting, provide_recipient, provide_message):
        assert use_message() == "Hello World"


async def test_async_injection():
    @provider.asyncfunction
    async def provide_greeting() -> Greeting:
        return Greeting("Hello")

    @provider.asyncfunction
    async def provide_recipient() -> Recipient:
        return Recipient("World")

    @provider.asyncfunction
    async def provide_message(*, greeting: Greeting = required, recipient: Recipient = required) -> Message:
        return Message(f"{greeting} {recipient}")

    @injector.asyncfunction
    async def use_message(*, message: Message = required):
        return message

    with solution(provide_greeting, provide_recipient, provide_message):
        assert await use_message() == "Hello World"


async def test_sync_and_async_providers_do_not_overwrite_each_other():
    @provider.function
    def sync_provide_message() -> Message:
        return Message("Hello, Sync")

    @provider.asyncfunction
    async def async_provide_message() -> Message:
        return Message("World, Async")

    @injector.function
    def sync_use_message(*, message: Message = required):
        return message

    @injector.asyncfunction
    async def async_use_message(*, message: Message = required):
        return message

    with solution(sync_provide_message, async_provide_message):
        assert sync_use_message() == "Hello, Sync"
        assert await async_use_message() == "World, Async"


async def test_async_provider_can_depend_on_sync_provider():
    @provider.function
    def provide_greeting() -> Greeting:
        return Greeting("Hello")

    @provider.asyncfunction
    async def provide_message(*, greeting: Greeting = required) -> Message:
        return Message(f"{greeting} World")

    @injector.asyncfunction
    async def use_message(*, message: Message = required):
        return message

    with solution(provide_greeting, provide_message):
        assert await use_message() == "Hello World"


async def test_sync_provider_cannot_depend_on_async_provider():
    @provider.asyncfunction
    async def provide_greeting() -> Greeting:
        raise AssertionError  # nocov

    @provider.function
    def provide_message(*, _: Greeting = required) -> Message:
        raise AssertionError  # nocov

    @injector.function
    async def use_message(*, _: Message = required):
        raise AssertionError  # nocov

    with (
        pytest.raises(SolutionError, match=r"No provider for .*"),
        solution(provide_greeting, provide_message),
    ):
        pass  # nocov


def test_union_dependency_is_disallowed():
    with pytest.raises(TypeError, match=r"Cannot use Union type"):

        @provider.function
        def provide_greeting() -> Greeting | Recipient:
            raise AssertionError


@pytest.mark.parametrize("returns", [str, list, list[str]], ids=str)
def test_disallow_builtin_type_as_provided_depdency(returns):

    def f():
        raise AssertionError  # nocov

    f.__annotations__["return"] = returns

    with pytest.raises(TypeError, match=r"Cannot use built-in type"):
        provider.function(f)


def test_disallow_builtin_type_as_injector_dependency():
    with pytest.raises(TypeError, match=r"Cannot use built-in type"):

        @injector.function
        def use_greeting(*, _: str = required):  # nocov
            raise AssertionError


@pytest.mark.parametrize("returns", [Any, TypeVar("T")], ids=str)
def test_solution_requires_provider_types_to_be_concrete(returns):

    def f():
        raise AssertionError  # nocov

    f.__annotations__["return"] = returns

    f_provider = provider.function(f)

    with pytest.raises(TypeError, match=r"Can only provide concrete type"), solution(f_provider):
        raise AssertionError  # nocov


def test_allow_provider_return_any_if_concrete_type_declared_before_entering_scope():

    @provider.function
    def greeting() -> Any:
        return "Hello"

    @injector.function
    def get_greeting(*, greeting: Greeting = required) -> Greeting:
        return greeting

    with solution(greeting[Greeting]):
        assert get_greeting() == "Hello"


def test_allow_provider_return_typevar_if_concrete_type_declared_before_entering_scope():

    @provider.function
    def make_string(cls: Callable[[str], T], string: str) -> T:
        return cls(string)

    @injector.function
    def get_greeting(*, greeting: Greeting = required) -> Greeting:
        return greeting

    with solution(make_string[Greeting].bind(Greeting, "Hello")):
        assert get_greeting() == "Hello"


def test_generic_with_provides_inference_function():

    @provider.function(provides=lambda cls, *a, **kw: cls)
    def make_string(cls: Callable[[str], T], string: str) -> T:
        return cls(string)

    @injector.function
    def get_greeting(*, greeting: Greeting = required) -> Greeting:
        return greeting

    with solution(make_string.bind(Greeting, "Hello")):
        assert get_greeting() == "Hello"


def test_dependency_reused_across_providers():
    call_count = 0

    @provider.function
    def provide_greeting() -> Greeting:
        nonlocal call_count
        call_count += 1
        return Greeting("Hello")

    @provider.function
    def provider_side_effect(*, _: Greeting = required) -> SideEffect:
        return SideEffect(None)

    @injector.function
    def get_greeting(*, greeting: Greeting = required, _: SideEffect = required) -> Greeting:
        return greeting

    with solution(provide_greeting, provider_side_effect):
        get_greeting()
        assert call_count == 1


def test_overwritten_value_is_used_by_providers():
    assert False


def test_overwritten_value_causes_descendant_providers_to_reevaluate():
    assert False
