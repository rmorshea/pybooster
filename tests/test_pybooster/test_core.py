from __future__ import annotations

from asyncio import wait_for
from collections.abc import Callable  # noqa: TCH003
from collections.abc import Iterator  # noqa: TCH003
from dataclasses import dataclass
from typing import Any
from typing import NewType
from typing import TypeVar

import pytest
from anyio import Event

from pybooster import injector
from pybooster import provider
from pybooster import required
from pybooster import solution
from pybooster.core.injector import current
from pybooster.core.injector import overwrite
from pybooster.types import InjectionError
from pybooster.types import SolutionError

T = TypeVar("T")

Greeting = NewType("Greeting", str)
Recipient = NewType("Recipient", str)
Message = NewType("Message", str)
SideEffect = NewType("SideEffect", None)


def test_sync_injection():

    @provider.function
    def greeting_provider() -> Greeting:
        return Greeting("Hello")

    @provider.function
    def recipient_provider() -> Recipient:
        return Recipient("World")

    @provider.function
    def message_provider(*, greeting: Greeting = required, recipient: Recipient = required) -> Message:
        return Message(f"{greeting} {recipient}")

    @injector.function
    def use_message(*, message: Message = required):
        return message

    with solution(greeting_provider, recipient_provider, message_provider):
        assert use_message() == "Hello World"


async def test_async_injection():
    @provider.asyncfunction
    async def greeting_provider() -> Greeting:
        return Greeting("Hello")

    @provider.asyncfunction
    async def recipient_provider() -> Recipient:
        return Recipient("World")

    @provider.asyncfunction
    async def message_provider(*, greeting: Greeting = required, recipient: Recipient = required) -> Message:
        return Message(f"{greeting} {recipient}")

    @injector.asyncfunction
    async def use_message(*, message: Message = required):
        return message

    with solution(greeting_provider, recipient_provider, message_provider):
        assert await use_message() == "Hello World"


async def test_sync_and_async_providers_do_not_overwrite_each_other():
    @provider.function
    def sync_message_provider() -> Message:
        return Message("Hello, Sync")

    @provider.asyncfunction
    async def async_message_provider() -> Message:
        return Message("World, Async")

    @injector.function
    def sync_use_message(*, message: Message = required):
        return message

    @injector.asyncfunction
    async def async_use_message(*, message: Message = required):
        return message

    with solution(sync_message_provider, async_message_provider):
        assert sync_use_message() == "Hello, Sync"
        assert await async_use_message() == "World, Async"


async def test_async_provider_can_depend_on_sync_provider():
    @provider.function
    def greeting_provider() -> Greeting:
        return Greeting("Hello")

    @provider.asyncfunction
    async def message_provider(*, greeting: Greeting = required) -> Message:
        return Message(f"{greeting} World")

    @injector.asyncfunction
    async def use_message(*, message: Message = required):
        return message

    with solution(greeting_provider, message_provider):
        assert await use_message() == "Hello World"


async def test_sync_provider_cannot_depend_on_async_provider():
    @provider.asyncfunction
    async def greeting_provider() -> Greeting:
        raise AssertionError  # nocov

    @provider.function
    def message_provider(*, _: Greeting = required) -> Message:
        raise AssertionError  # nocov

    @injector.function
    async def use_message(*, _: Message = required):
        raise AssertionError  # nocov

    with (
        pytest.raises(SolutionError, match=r"No provider for .*"),
        solution(greeting_provider, message_provider),
    ):
        pass  # nocov


def test_union_dependency_is_disallowed():
    with pytest.raises(TypeError, match=r"Cannot use Union type"):

        @provider.function
        def greeting_provider() -> Greeting | Recipient:
            raise AssertionError  # nocov


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
    def greeting_provider() -> Greeting:
        nonlocal call_count
        call_count += 1
        return Greeting("Hello")

    @provider.function
    def provider_side_effect(*, _: Greeting = required) -> SideEffect:
        return SideEffect(None)

    @injector.function
    def get_greeting(*, greeting: Greeting = required, _: SideEffect = required) -> Greeting:
        return greeting

    with solution(greeting_provider, provider_side_effect):
        get_greeting()
        assert call_count == 1


def test_dependency_not_reused_by_inner_calls():
    call_count = 0
    exit_count = 0

    @provider.iterator
    def greeting_provider() -> Iterator[Greeting]:
        nonlocal call_count
        call_count += 1
        try:
            yield Greeting("Hello")
        finally:
            nonlocal exit_count
            exit_count += 1

    @injector.function
    def get_greeting_inner(*, greeting: Greeting = required) -> Greeting:
        assert call_count == 2
        assert exit_count == 0
        return greeting

    @injector.function
    def get_greeting_outer(*, greeting: Greeting = required) -> Greeting:
        assert call_count == 1
        inner_greeting = get_greeting_inner()
        assert exit_count == 1
        return Greeting(f"{greeting} {inner_greeting}")

    with solution(greeting_provider):
        assert get_greeting_outer() == "Hello Hello"
        assert exit_count == 2
        assert call_count == 2


UserId = NewType("UserId", int)


@dataclass
class Profile:
    name: str
    bio: str


def test_overwritten_value_causes_descendant_providers_to_reevaluate():
    db = {
        1: Profile(name="Alice", bio="Alice's bio"),
        2: Profile(name="Bob", bio="Bob's bio"),
    }

    call_count = 0

    @provider.function
    def user_id_provider() -> UserId:
        return UserId(1)

    @provider.function
    def profile_provider(*, user_id: UserId = required) -> Profile:
        nonlocal call_count
        call_count += 1
        return db[user_id]

    @injector.function
    def get_profile_summary(*, user_id: UserId = required, profile: Profile = required) -> str:
        return f"#{user_id} {profile.name}: {profile.bio}"

    with solution(user_id_provider, profile_provider):
        with current(Profile):
            assert call_count == 1
            assert get_profile_summary() == "#1 Alice: Alice's bio"
            assert call_count == 1
            assert get_profile_summary(user_id=UserId(2)) == "#2 Bob: Bob's bio"
            assert call_count == 2


def test_raise_on_missing_params():
    @injector.function
    def use_message(*, _: Message = required):
        raise AssertionError  # nocov

    with pytest.raises(InjectionError, match=r"Missing providers for parameters: .*"):
        use_message()


async def test_async_provider_can_depend_on_sync_and_async_providers_at_the_same_time():
    @provider.function
    def greeting_provider() -> Greeting:
        return Greeting("Hello")

    @provider.asyncfunction
    async def recipient_provider() -> Recipient:
        return Recipient("World")

    @provider.asyncfunction
    async def message_provider(*, greeting: Greeting = required, recipient: Recipient = required) -> Message:
        return Message(f"{greeting} {recipient}")

    @injector.asyncfunction
    async def use_message(*, message: Message = required):
        return message

    with solution(greeting_provider, recipient_provider, message_provider):
        assert await use_message() == "Hello World"


async def test_async_providers_are_executed_concurrently_if_possible():
    did_begin_greeting = Event()
    did_begin_recipient = Event()

    @provider.asyncfunction
    async def greeting_provider() -> Greeting:
        did_begin_greeting.set()
        await did_begin_recipient.wait()
        return Greeting("Hello")

    @provider.asyncfunction
    async def recipient_provider() -> Recipient:
        did_begin_recipient.set()
        await did_begin_greeting.wait()
        return Recipient("World")

    @provider.asyncfunction
    async def message_provider(*, greeting: Greeting = required, recipient: Recipient = required) -> Message:
        return Message(f"{greeting} {recipient}")

    @injector.asyncfunction
    async def use_message(*, message: Message = required):
        return message

    with solution(greeting_provider, recipient_provider, message_provider):
        assert await wait_for(use_message(), 3) == "Hello World"


def test_cannot_enter_current_context_more_than_once():
    @provider.function
    def greeting_provider() -> Greeting:
        return Greeting("Hello")

    with solution(greeting_provider):
        ctx = current(Greeting)
        with ctx:
            with pytest.raises(RuntimeError, match=r"Cannot reuse a context manager."):
                with ctx:
                    raise AssertionError  # nocov


async def test_cannot_async_enter_current_context_more_than_once():
    @provider.function
    def greeting_provider() -> Greeting:
        return Greeting("Hello")

    with solution(greeting_provider):
        ctx = current(Greeting)
        async with ctx:
            with pytest.raises(RuntimeError, match=r"Cannot reuse a context manager."):
                async with ctx:
                    raise AssertionError  # nocov


def test_cannot_enter_overwrite_context_more_than_once():
    ctx = overwrite({Greeting: "Hi"})
    with ctx:
        with pytest.raises(RuntimeError, match=r"Cannot reuse a context manager."):
            with ctx:
                raise AssertionError  # nocov


def test_cannot_bind_required_provider_parameters():
    @provider.function
    def message_provider(*, greeting: Greeting = required) -> Message:
        raise AssertionError(greeting)  # nocov

    with pytest.raises(TypeError, match="Cannot bind dependency parameters"):
        message_provider.bind(greeting=Greeting("Hello"))


def test_can_call_provider_directly():
    @provider.function
    def greeting_provider() -> Greeting:
        return Greeting("Hello")

    with greeting_provider() as greeting:
        assert greeting == "Hello"


async def test_can_call_async_provider_directly():
    @provider.asyncfunction
    async def greeting_provider() -> Greeting:
        return Greeting("Hello")

    async with greeting_provider() as greeting:
        assert greeting == "Hello"