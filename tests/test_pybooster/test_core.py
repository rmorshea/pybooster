from __future__ import annotations

from typing import Any
from typing import Callable
from typing import NewType
from typing import TypeVar

import pytest

from pybooster import injector
from pybooster import provider
from pybooster import required
from pybooster import solution
from pybooster.core.types import ProviderMissingError

T = TypeVar("T")

Greeting = NewType("Greeting", str)
Recipient = NewType("Recipient", str)
Message = NewType("Message", str)
SideEffect = NewType("SideEffect", None)


def test_sync_injection():

    @provider.function
    def greeting() -> Greeting:
        return Greeting("Hello")

    @provider.function
    def recipient() -> Recipient:
        return Recipient("World")

    @provider.function
    def message(*, greeting: Greeting = required, recipient: Recipient = required) -> Message:
        return Message(f"{greeting} {recipient}")

    @injector.function
    def use_message(*, message: Message = required):
        return message

    with solution(greeting, recipient, message):
        assert use_message() == "Hello World"


async def test_async_injection():
    @provider.asyncfunction
    async def greeting() -> Greeting:
        return Greeting("Hello")

    @provider.asyncfunction
    async def recipient() -> Recipient:
        return Recipient("World")

    @provider.asyncfunction
    async def message(*, greeting: Greeting = required, recipient: Recipient = required) -> Message:
        return Message(f"{greeting} {recipient}")

    @injector.asyncfunction
    async def use_message(*, message: Message = required):
        return message

    with solution(greeting, recipient, message):
        assert await use_message() == "Hello World"


async def test_sync_and_async_providers_do_not_overwrite_each_other():
    @provider.function
    def sync_message() -> Message:
        return Message("Hello, Sync")

    @provider.asyncfunction
    async def async_message() -> Message:
        return Message("World, Async")

    @injector.function
    def use_sync_message(*, message: Message = required):
        return message

    @injector.asyncfunction
    async def use_async_message(*, message: Message = required):
        return message

    with solution(sync_message, async_message):
        assert use_sync_message() == "Hello, Sync"
        assert await use_async_message() == "World, Async"


async def test_async_provider_can_depend_on_sync_provider():
    @provider.function
    def greeting() -> Greeting:
        return Greeting("Hello")

    @provider.asyncfunction
    async def message(*, greeting: Greeting = required) -> Message:
        return Message(f"{greeting} World")

    @injector.asyncfunction
    async def use_message(*, message: Message = required):
        return message

    with solution(greeting, message):
        assert await use_message() == "Hello World"


async def test_sync_provider_cannot_depend_on_async_provider():
    @provider.asyncfunction
    async def greeting() -> Greeting:
        raise AssertionError  # nocov

    @provider.function
    def message(*, _: Greeting = required) -> Message:
        raise AssertionError  # nocov

    @injector.function
    async def use_message(*, _: Message = required):
        raise AssertionError  # nocov

    with (
        pytest.raises(ProviderMissingError, match=r"No sync providers for .*"),
        solution(greeting, message),
    ):
        pass  # nocov


def test_union_dependency_is_resolution_in_order():
    @provider.function
    def greeting() -> Greeting:
        return Greeting("Hello")

    @provider.function
    def recipient() -> Recipient:
        return Recipient("World")

    @injector.function
    def get_greeting_or_recipient(*, greeting_or_recipient: Greeting | Recipient = required):
        return greeting_or_recipient

    with solution(greeting, recipient):
        assert get_greeting_or_recipient() == "Hello"

    with solution(recipient, greeting):
        assert get_greeting_or_recipient() == "Hello"

    with solution(greeting):
        assert get_greeting_or_recipient() == "Hello"

    with solution(recipient):
        assert get_greeting_or_recipient() == "World"


def test_disallow_builtin_type_as_provided_depdency():
    @provider.function
    def greeting() -> str:
        raise AssertionError  # nocov

    with pytest.raises(TypeError, match=r"Cannot provide built-in type"):
        with solution(greeting):  # nocov
            raise AssertionError


def test_disallow_builtin_type_as_injector_dependency():
    with pytest.raises(TypeError, match=r"Cannot provide built-in type"):

        @injector.function
        def use_greeting(*, _: str = required):  # nocov
            raise AssertionError


@pytest.mark.parametrize("returns", [Any, object, TypeVar("T")], ids=str)
def test_provider_must_have_concrete_type_when_entering_scope(returns):

    def f():
        raise AssertionError  # nocov

    f.__annotations__["returns"] = returns

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
    def greeting() -> Greeting:
        nonlocal call_count
        call_count += 1
        return Greeting("Hello")

    @provider.function
    def provider_uses_greeting(*, _: Greeting = required) -> SideEffect:
        return SideEffect(None)

    @injector.function
    def get_greeting(*, greeting: Greeting = required, _: SideEffect = required) -> Greeting:
        return greeting

    with solution(greeting, provider_uses_greeting):
        get_greeting()
        assert call_count == 1