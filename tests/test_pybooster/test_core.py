from __future__ import annotations

from asyncio import wait_for
from collections.abc import Callable
from collections.abc import Iterator
from dataclasses import dataclass
from typing import TYPE_CHECKING
from typing import Any
from typing import NewType
from typing import TypeVar

import pytest
from anyio import Event

from pybooster import injector
from pybooster import provider
from pybooster import required
from pybooster import solved
from pybooster.types import InjectionError
from pybooster.types import SolutionError

if TYPE_CHECKING:
    from collections.abc import Callable
    from collections.abc import Iterator

T = TypeVar("T")

Greeting = NewType("Greeting", str)
Recipient = NewType("Recipient", str)
Message = NewType("Message", str)
SideEffect = NewType("SideEffect", None)

# Use to make a graph of the form:
#
#     Top
#    /   \
#  Left  Right
#    \   /
#    Bottom
Top = NewType("Top", str)
Left = NewType("Left", str)
Right = NewType("Right", str)
Bottom = NewType("Bottom", str)


def test_sync_function_injection():
    @provider.function
    def greeting_provider() -> Greeting:
        return Greeting("Hello")

    @injector.function
    def get_message(*, greeting: Greeting = required):
        return f"{greeting} World"

    with solved(greeting_provider):
        assert get_message() == "Hello World"


def test_sync_iterator_injection():
    @provider.function
    def greeting_provider() -> Greeting:
        return Greeting("Hello")

    @injector.iterator
    def get_message(*, greeting: Greeting = required):
        yield f"{greeting} World"

    with solved(greeting_provider):
        assert list(get_message()) == ["Hello World"]


def test_sync_context_manager_injection():
    @provider.function
    def greeting_provider() -> Greeting:
        return Greeting("Hello")

    @injector.contextmanager
    def get_message(*, greeting: Greeting = required):
        yield f"{greeting} World"

    with solved(greeting_provider):
        with get_message() as message:
            assert message == "Hello World"


async def test_async_function_injection():
    @provider.asyncfunction
    async def greeting_provider() -> Greeting:
        return Greeting("Hello")

    @injector.asyncfunction
    async def get_message(*, greeting: Greeting = required):
        return f"{greeting} World"

    with solved(greeting_provider):
        assert await get_message() == "Hello World"


async def test_async_iterator_injection():
    @provider.asyncfunction
    async def greeting_provider() -> Greeting:
        return Greeting("Hello")

    @injector.asynciterator
    async def get_message(*, greeting: Greeting = required):
        yield f"{greeting} World"

    with solved(greeting_provider):
        assert [v async for v in get_message()] == ["Hello World"]


async def test_async_context_manager_injection():
    @provider.asyncfunction
    async def greeting_provider() -> Greeting:
        return Greeting("Hello")

    @injector.asynccontextmanager
    async def get_message(*, greeting: Greeting = required):
        yield f"{greeting} World"

    with solved(greeting_provider):
        async with get_message() as message:
            assert message == "Hello World"


async def test_sync_and_async_providers_do_not_overwrite_each_other():
    @provider.function
    def sync_message_provider() -> Message:
        return Message("Hello, Sync")

    @provider.asyncfunction
    async def async_message_provider() -> Message:
        return Message("World, Async")

    @injector.function
    def sync_get_message(*, message: Message = required):
        return message

    @injector.asyncfunction
    async def async_get_message(*, message: Message = required):
        return message

    with solved(sync_message_provider, async_message_provider):
        assert sync_get_message() == "Hello, Sync"
        assert await async_get_message() == "World, Async"


async def test_async_provider_can_depend_on_sync_provider():
    @provider.function
    def greeting_provider() -> Greeting:
        return Greeting("Hello")

    @provider.asyncfunction
    async def message_provider(*, greeting: Greeting = required) -> Message:
        return Message(f"{greeting} World")

    @injector.asyncfunction
    async def get_message(*, message: Message = required):
        return message

    with solved(greeting_provider, message_provider):
        assert await get_message() == "Hello World"


async def test_sync_provider_cannot_depend_on_async_provider():
    @provider.asyncfunction
    async def greeting_provider() -> Greeting:
        raise AssertionError

    @provider.function
    def message_provider(*, _: Greeting = required) -> Message:
        raise AssertionError

    @injector.function
    async def get_message(*, _: Message = required):
        raise AssertionError

    with (
        pytest.raises(SolutionError, match=r"No provider for .*"),
        solved(greeting_provider, message_provider),
    ):
        pass  # nocov


@pytest.mark.parametrize("returns", [str, list, list[str]], ids=str)
def test_disallow_builtin_type_as_provided_depdency(returns):
    def f():
        raise AssertionError

    f.__annotations__["return"] = returns

    with pytest.raises(TypeError, match=r"Cannot use built-in type"):
        provider.function(f)


def test_disallow_builtin_type_as_injector_dependency():
    with pytest.raises(TypeError, match=r"Cannot use built-in type"):

        @injector.function
        def bad(*, _: str = required):  # nocov
            raise AssertionError


@pytest.mark.parametrize("returns", [Any, TypeVar("T")], ids=str)
def test_solution_requires_provider_types_to_be_concrete(returns):
    def f():
        raise AssertionError

    f.__annotations__["return"] = returns

    f_provider = provider.function(f)

    with pytest.raises(TypeError, match=r"Can only provide concrete type"), solved(f_provider):
        raise AssertionError


def test_allow_provider_return_any_if_concrete_type_declared_before_entering_scope():
    @provider.function
    def greeting() -> Any:
        return "Hello"

    @injector.function
    def get_greeting(*, greeting: Greeting = required) -> Greeting:
        return greeting

    with solved(greeting[Greeting]):
        assert get_greeting() == "Hello"


def test_allow_provider_return_typevar_if_concrete_type_declared_before_entering_scope():
    @provider.function
    def make_string(cls: Callable[[str], T], string: str) -> T:
        return cls(string)

    @injector.function
    def get_greeting(*, greeting: Greeting = required) -> Greeting:
        return greeting

    with solved(make_string[Greeting].bind(Greeting, "Hello")):
        assert get_greeting() == "Hello"


def test_generic_with_provides_inference_function():
    @provider.function(provides=lambda cls, *a, **kw: cls)
    def make_string(cls: Callable[[str], T], string: str) -> T:
        return cls(string)

    @injector.function
    def get_greeting(*, greeting: Greeting = required) -> Greeting:
        return greeting

    with solved(make_string.bind(Greeting, "Hello")):
        assert get_greeting() == "Hello"


def test_sync_dependencies_reused_across_providers():
    call_count = 0

    @provider.function
    def top_provider() -> Top:
        nonlocal call_count
        call_count += 1
        return Top("top")

    @provider.function
    def left_provider(*, _top: Top = required) -> Left:
        return Left("left")

    @provider.function
    def right_provider(*, _top: Top = required) -> Right:
        return Right("right")

    @provider.function
    def bottom_provider(*, _left: Left = required, _right: Right = required) -> Bottom:
        return Bottom("bottom")

    @injector.function
    def get_bottom(*, bottom: Bottom = required) -> Bottom:
        return bottom

    with solved(top_provider, left_provider, right_provider, bottom_provider):
        assert get_bottom() == "bottom"
        assert call_count == 1


async def test_async_dependencies_reused_across_providers():
    call_count = 0

    @provider.asyncfunction
    async def top_provider() -> Top:
        nonlocal call_count
        call_count += 1
        return Top("top")

    @provider.asyncfunction
    async def left_provider(*, _top: Top = required) -> Left:
        return Left("left")

    @provider.asyncfunction
    async def right_provider(*, _top: Top = required) -> Right:
        return Right("right")

    @provider.asyncfunction
    async def bottom_provider(*, _left: Left = required, _right: Right = required) -> Bottom:
        return Bottom("bottom")

    @injector.asyncfunction
    async def get_bottom(*, bottom: Bottom = required) -> Bottom:
        return bottom

    with solved(top_provider, left_provider, right_provider, bottom_provider):
        assert (await get_bottom()) == "bottom"
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

    with solved(greeting_provider):
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

    with solved(user_id_provider, profile_provider):
        with injector.shared(Profile):
            assert call_count == 1
            assert get_profile_summary() == "#1 Alice: Alice's bio"
            assert call_count == 1
            assert get_profile_summary(user_id=UserId(2)) == "#2 Bob: Bob's bio"
            assert call_count == 2


def test_raise_on_missing_params():
    @injector.function
    def get_message(*, _: Message = required):
        raise AssertionError

    with pytest.raises(InjectionError, match=r"Missing providers for .*"):
        get_message()


async def test_async_provider_can_depend_on_sync_and_async_providers_at_the_same_time():
    @provider.function
    def greeting_provider() -> Greeting:
        return Greeting("Hello")

    @provider.asyncfunction
    async def recipient_provider() -> Recipient:
        return Recipient("World")

    @provider.asyncfunction
    async def message_provider(
        *, greeting: Greeting = required, recipient: Recipient = required
    ) -> Message:
        return Message(f"{greeting} {recipient}")

    @injector.asyncfunction
    async def get_message(*, message: Message = required):
        return message

    with solved(greeting_provider, recipient_provider, message_provider):
        assert await get_message() == "Hello World"


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
    async def message_provider(
        *, greeting: Greeting = required, recipient: Recipient = required
    ) -> Message:
        return Message(f"{greeting} {recipient}")

    @injector.asyncfunction
    async def get_message(*, message: Message = required):
        return message

    with solved(greeting_provider, recipient_provider, message_provider):
        assert await wait_for(get_message(), 3) == "Hello World"


def test_cannot_enter_shared_context_more_than_once():
    @provider.function
    def greeting_provider() -> Greeting:
        return Greeting("Hello")

    with solved(greeting_provider):
        ctx = injector.shared(Greeting)
        with ctx:
            with pytest.raises(RuntimeError, match=r"Cannot reuse a context manager."):
                with ctx:
                    raise AssertionError


async def test_cannot_async_enter_shared_context_more_than_once():
    @provider.function
    def greeting_provider() -> Greeting:
        return Greeting("Hello")

    with solved(greeting_provider):
        ctx = injector.shared(Greeting)
        async with ctx:
            with pytest.raises(RuntimeError, match=r"Cannot reuse a context manager."):
                async with ctx:
                    raise AssertionError


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


def test_solution_requires_at_least_one_provider():
    with pytest.raises(ValueError, match=r"At least one provider must be given"):
        with solved():
            raise AssertionError


def test_cannot_provide_union():
    @provider.function
    def greeting_provider() -> Greeting | Recipient:  # nocov
        raise AssertionError

    with pytest.raises(TypeError, match=r"Cannot provide a union type .*"):
        with solved(greeting_provider):
            raise AssertionError


async def test_async_func_requires_only_sync_providers():
    @provider.function
    def greeting_provider() -> Greeting:
        return Greeting("Hello")

    @provider.function
    def recipient_provider() -> Recipient:
        return Recipient("World")

    @injector.asyncfunction
    async def get_message(*, greeting: Greeting = required, recipient: Recipient = required):
        return f"{greeting}, {recipient}!"

    with solved(greeting_provider, recipient_provider):
        assert (await get_message()) == "Hello, World!"


def test_injecting_current_value_does_not_invalidate_providers():
    call_count = 0

    @provider.function
    def greeting_provider() -> Greeting:
        return Greeting("Hello")

    @provider.function
    def message_provider(*, greeting: Greeting = required) -> Message:
        nonlocal call_count
        call_count += 1
        return Message(f"{greeting}, World!")

    @injector.function
    def get_double_greeting_message(*, greeting: Greeting = required, message: Message = required):
        return f"{greeting} {message}"

    with solved(greeting_provider, message_provider):
        with injector.shared(Greeting, Message) as values:
            assert call_count == 1
            assert get_double_greeting_message(greeting=values[Greeting]) == "Hello Hello, World!"
            assert call_count == 1


async def test_async_shared_context_with_dependencies_and_overrides():
    @provider.asyncfunction
    async def greeting_provider() -> Greeting:
        raise AssertionError  # nocov

    @provider.asyncfunction
    async def recipient_provider() -> Recipient:
        raise AssertionError  # nocov

    with solved(greeting_provider, recipient_provider):
        async with injector.shared((Greeting, "Hello"), (Recipient, "World")) as values:
            assert values == {Greeting: "Hello", Recipient: "World"}
