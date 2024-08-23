import asyncio
from collections.abc import AsyncIterator
from collections.abc import Iterator
from dataclasses import dataclass
from typing import NewType

import pytest

from ninject import current
from ninject import default
from ninject import inject
from ninject import let
from ninject import provider
from ninject import required

Greeting = NewType("Greeting", str)
Recipient = NewType("Recipient", str)
Message = NewType("Message", str)

MessageContent = tuple[Greeting, Recipient]


@inject
def sync_use_greeting(*, greeting: Greeting = required):
    return f"{greeting}, World!"


@inject
async def async_use_greeting(*, greeting: Greeting = required):
    return f"{greeting}, World!"


@inject
def sync_use_message(*, message: Message = required):
    return message


@inject
async def async_use_message(*, message: Message = required):
    return message


@inject
def sync_use_message_content_parts(*, greeting: Greeting = required, recipient: Recipient = required):
    return f"{greeting}, {recipient}!"


@inject
async def async_use_message_content_parts(*, greeting: Greeting = required, recipient: Recipient = required):
    return f"{greeting}, {recipient}!"


def test_inject_single_dependency_from_sync_function_provider():

    @provider
    def provide_greeting() -> Greeting:
        return Greeting("Hello")

    with provide_greeting():
        assert sync_use_greeting() == "Hello, World!"


async def test_inject_single_dependency_from_async_function_provider():

    @provider
    async def provide_greeting() -> Greeting:
        return Greeting("Hello")

    with provide_greeting():
        assert await async_use_greeting() == "Hello, World!"


def test_inject_single_dependency_from_sync_generator_provider():

    did_cleanup = False

    @provider
    def provide_greeting() -> Iterator[Greeting]:
        try:
            yield Greeting("Hello")
        finally:
            nonlocal did_cleanup
            did_cleanup = True

    with provide_greeting():
        assert not did_cleanup
        assert sync_use_greeting() == "Hello, World!"
        assert did_cleanup


async def test_inject_single_dependency_from_async_generator_provider():
    did_cleanup = False

    @provider
    async def provide_greeting() -> AsyncIterator[Greeting]:
        try:
            yield Greeting("Hello")
        finally:
            nonlocal did_cleanup
            did_cleanup = True

    with provide_greeting():
        assert not did_cleanup
        assert await async_use_greeting() == "Hello, World!"
        assert did_cleanup


def test_inject_single_dependency_from_sync_context_manager_provider():

    did_cleanup = False

    @provider
    class ProvideGreeting:
        def __enter__(self) -> Greeting:
            return Greeting("Hello")

        def __exit__(self, etype, evalue, etrace):
            nonlocal did_cleanup
            did_cleanup = True

    with ProvideGreeting():
        assert not did_cleanup
        assert sync_use_greeting() == "Hello, World!"
        assert did_cleanup


async def test_inject_single_dependency_from_async_context_manager_provider():
    did_cleanup = False

    @provider
    class ProvideGreeting:
        async def __aenter__(self) -> Greeting:
            return Greeting("Hello")

        async def __aexit__(self, etype, evalue, etrace):
            nonlocal did_cleanup
            did_cleanup = True

    with ProvideGreeting():
        assert not did_cleanup
        assert await async_use_greeting() == "Hello, World!"
        assert did_cleanup


def test_nesting_sync_providers_contexts():
    @provider
    def provide_hello_greeting() -> Greeting:
        return Greeting("Hello")

    @provider
    def provide_good_morning_greeting() -> Greeting:
        return Greeting("Good morning")

    with provide_hello_greeting():
        assert sync_use_greeting() == "Hello, World!"
        with provide_good_morning_greeting():
            assert sync_use_greeting() == "Good morning, World!"
        assert sync_use_greeting() == "Hello, World!"


async def test_nesting_async_providers_contexts():
    @provider
    async def provide_hello_greeting() -> Greeting:
        return Greeting("Hello")

    @provider
    async def provide_good_morning_greeting() -> Greeting:
        return Greeting("Good morning")

    with provide_hello_greeting():
        assert await async_use_greeting() == "Hello, World!"
        with provide_good_morning_greeting():
            assert await async_use_greeting() == "Good morning, World!"
        assert await async_use_greeting() == "Hello, World!"


def test_sync_provider_with_sync_dependency():
    @provider
    def provide_greeting() -> Greeting:
        return Greeting("Hello")

    @provider
    def provide_message(*, greeting: Greeting = required) -> Message:
        return Message(f"{greeting}, World!")

    with provide_greeting(), provide_message():
        assert sync_use_message() == "Hello, World!"


async def test_sync_provider_with_async_dependency_used_in_async_function():
    @provider
    async def provide_greeting() -> Greeting:
        return Greeting("Hello")

    @provider
    def provide_message(*, greeting: Greeting = required) -> Message:
        return Message(f"{greeting}, World!")

    with provide_greeting(), provide_message():
        assert await async_use_message() == "Hello, World!"


def test_sync_provider_with_async_dependency_used_in_sync_function():
    @provider
    async def provide_greeting() -> Greeting: ...

    @provider
    def provide_message(*, _: Greeting = required) -> Message: ...

    with provide_greeting(), provide_message():
        with pytest.raises(RuntimeError, match=r"Cannot use an async provider .* in a sync context"):
            sync_use_message()


async def test_async_provider_with_sync_dependency_used_in_async_function():

    @provider
    def provide_greeting() -> Greeting:
        return Greeting("Hello")

    @provider
    async def provide_message(*, greeting: Greeting = required) -> Message:
        return Message(f"{greeting}, World!")

    with provide_greeting(), provide_message():
        assert await async_use_message() == "Hello, World!"


def test_reuse_sync_provider():

    @provider
    def provide_greeting() -> Greeting:
        return Greeting("Hello")

    @inject
    def use_greeting(*, greeting: Greeting = required):
        return greeting

    @inject
    def use_greeting_again(*, greeting: Greeting = required):
        return f"{greeting} {use_greeting()}"

    with provide_greeting():
        assert use_greeting_again() == "Hello Hello"
        assert use_greeting() == Greeting("Hello")


async def test_reuse_async_provider():

    @provider
    async def provide_greeting() -> Greeting:
        return Greeting("Hello")

    @inject
    async def use_greeting(*, greeting: Greeting = required):
        return greeting

    @inject
    async def use_greeting_again(*, greeting: Greeting = required):
        return f"{greeting} {await use_greeting()}"

    with provide_greeting():
        assert await use_greeting_again() == "Hello Hello"
        assert await use_greeting() == Greeting("Hello")


def test_unsupported_provider_type():

    with pytest.raises(TypeError, match="Unsupported provider type"):

        @provider
        class NotContextManager:
            pass

    class NotValidProvider:
        def __call__(self): ...

    with pytest.raises(TypeError, match="Unsupported provider type"):
        provider(NotValidProvider, cls=Greeting)  # type: ignore[reportArgumentType]


def test_provider_not_called_if_dependency_provided_explicitely():

    @provider
    def not_implemented() -> Greeting: ...

    with not_implemented():
        assert sync_use_greeting(greeting=Greeting("Hello")) == "Hello, World!"


async def test_inject_handles_exits_if_error_in_provider_for_each_injected_function_type():

    exit_called = False
    expected_error_message = "An expected error"

    @provider
    def provide_greeting() -> Iterator[Greeting]:
        try:
            yield Greeting("Hello")
        finally:
            nonlocal exit_called
            exit_called = True

    @inject
    def sync_func_raises_expected_error(*, _: Greeting = required):
        raise RuntimeError(expected_error_message)

    with pytest.raises(RuntimeError, match=expected_error_message):
        with provide_greeting():
            sync_func_raises_expected_error()

    assert exit_called
    exit_called = False

    @inject
    async def async_func_raises_expected_error(*, _: Greeting = required):
        raise RuntimeError(expected_error_message)

    with pytest.raises(RuntimeError, match=expected_error_message):
        with provide_greeting():
            await async_func_raises_expected_error()

    assert exit_called
    exit_called = False

    @inject
    def sync_gen_raises_expected_error(*, _: Greeting = required):
        yield
        raise RuntimeError(expected_error_message)

    with pytest.raises(RuntimeError, match=expected_error_message):
        with provide_greeting():
            list(sync_gen_raises_expected_error())

    assert exit_called
    exit_called = False

    @inject
    async def async_gen_raises_expected_error(*, _: Greeting = required):
        yield
        raise RuntimeError(expected_error_message)

    with pytest.raises(RuntimeError, match=expected_error_message):
        with provide_greeting():
            async for _ in async_gen_raises_expected_error():
                pass

    assert exit_called
    exit_called = False


async def test_concurrently_provide_many_dependencies_from_tuple():

    async def get_greeting():
        return Greeting("Hello")

    async def get_recipient():
        return Recipient("World")

    @provider
    async def provide_message_content() -> MessageContent:
        greeting, recipient = await asyncio.gather(get_greeting(), get_recipient())
        return greeting, recipient

    with provide_message_content():
        assert await async_use_message_content_parts() == "Hello, World!"
        assert await async_use_greeting() == "Hello, World!"


def test_sync_provide_many_dependencies_from_tuple():

    @provider
    def provide_message_content() -> MessageContent:
        return Greeting("Hello"), Recipient("World")

    with provide_message_content():
        assert sync_use_message_content_parts() == "Hello, World!"
        assert sync_use_greeting() == "Hello, World!"


def test_context_repr():

    @provider
    def provide_greeting() -> Greeting: ...

    @provider
    def provide_recipient() -> Recipient: ...

    assert repr(provide_greeting | provide_recipient) == f"Provider({Greeting}, {Recipient})"


def test_error_if_no_return_type_annotation():

    with pytest.raises(TypeError, match="Cannot determine return type"):

        @provider
        def provide_greeting(): ...


def test_cannot_inject_class():
    with pytest.raises(TypeError, match="Unsupported function type"):

        @inject
        class MyClass:
            def __init__(self, *, greeting: Greeting = required): ...


def test_let_dependency_equal_value():
    with let(Greeting, "Hello"):
        assert sync_use_greeting() == "Hello, World!"


def test_let_message_content_equal_value():
    with let(MessageContent, (Greeting("Hello"), Recipient("World"))):
        assert sync_use_message_content_parts() == "Hello, World!"


def test_merge_providers():

    @provider
    def provide_greeting_hello() -> Greeting:
        return Greeting("Hello")

    @provider
    def provide_recipient_world() -> Recipient:
        return Recipient("World")

    hello_world = provide_greeting_hello | provide_recipient_world

    @provider
    def provide_recipient_universe() -> Recipient:
        return Recipient("Universe")

    hello_universe = hello_world | provide_recipient_universe

    with hello_world():
        assert sync_use_message_content_parts() == "Hello, World!"

    with hello_universe():
        assert sync_use_message_content_parts() == "Hello, Universe!"


@dataclass(kw_only=True)
class MessageData:
    greeting: str
    recipient: str


def test_provide_user_defined_class_from_context():

    @provider
    def make_message_data() -> MessageData:
        return MessageData(greeting="Hello", recipient="World")

    @inject
    def use_message_data(*, message_data: MessageData = required):
        return f"{message_data.greeting}, {message_data.recipient}!"

    with make_message_data():
        assert use_message_data() == "Hello, World!"


def test_provide_user_defined_class_with_let():
    with let(MessageData(greeting="Hello", recipient="World")):

        @inject
        def use_message_data(*, message_data: MessageData = required):
            return f"{message_data.greeting}, {message_data.recipient}!"

        assert use_message_data() == "Hello, World!"


def test_let_invalid_type_arg():
    with pytest.raises(TypeError, match="Expected type"):

        with let(
            lambda _: None,  # nocov
            "Hello",
        ):
            raise AssertionError()  # nocov


def test_sync_access_current_value_from_sync_provider():

    @provider
    def provide_greeting() -> Greeting:
        return Greeting("Hello")

    with provide_greeting():
        with current(Greeting) as value:
            assert value == "Hello"


async def test_async_access_current_value_from_sync_provider():

    @provider
    def provide_greeting() -> Greeting:
        return Greeting("Hello")

    with provide_greeting():
        async with current(Greeting) as value:
            assert value == "Hello"


def test_sync_access_current_value_from_async_provider():

    @provider
    async def provide_greeting() -> Greeting:
        raise AssertionError()  # nocov

    with provide_greeting():
        with pytest.raises(RuntimeError, match="Cannot use an async provider .* in a sync context"):
            with current(Greeting):
                raise AssertionError()  # nocov


async def test_async_access_current_value_from_async_provider():

    @provider
    async def provide_greeting() -> Greeting:
        return Greeting("Hello")

    with provide_greeting():
        async with current(Greeting) as value:
            assert value == "Hello"


def test_sync_inject_with_default():

    @inject
    def use_greeting(*, greeting: Greeting = default["Hello"]):
        return greeting

    assert use_greeting() == "Hello"


async def test_async_inject_with_default():

    @inject
    async def use_greeting(*, greeting: Greeting = default["Hello"]):
        return greeting

    assert await use_greeting() == "Hello"


def test_sync_current_with_default():

    with current(Greeting, default="Hello") as value:
        assert value == "Hello"


async def test_async_current_with_default():
    async with current(Greeting, default="Hello") as value:
        assert value == "Hello"
