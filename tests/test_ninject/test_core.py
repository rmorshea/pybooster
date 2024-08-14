import asyncio
from collections.abc import AsyncIterator
from collections.abc import Iterator
from dataclasses import dataclass
from typing import NewType

import pytest

from ninject import Context
from ninject import inject
from ninject import let

Greeting = NewType("Greeting", str)
Recipient = NewType("Recipient", str)
Message = NewType("Message", str)

MessageContent = tuple[Greeting, Recipient]


@inject
def sync_use_greeting(*, greeting: Greeting = inject.ed):
    return f"{greeting}, World!"


@inject
async def async_use_greeting(*, greeting: Greeting = inject.ed):
    return f"{greeting}, World!"


@inject
def sync_use_message(*, message: Message = inject.ed):
    return message


@inject
async def async_use_message(*, message: Message = inject.ed):
    return message


@inject
def sync_use_message_content_parts(*, greeting: Greeting = inject.ed, recipient: Recipient = inject.ed):
    return f"{greeting}, {recipient}!"


@inject
async def async_use_message_content_parts(*, greeting: Greeting = inject.ed, recipient: Recipient = inject.ed):
    return f"{greeting}, {recipient}!"


def test_inject_repr():
    assert repr(inject) == "inject()"


def test_injected_repr():
    assert repr(inject.ed) == "INJECTED"


def test_inject_single_dependency_from_sync_function_provider():
    context = Context()

    @context.provides
    def provide_greeting() -> Greeting:
        return Greeting("Hello")

    with context:
        assert sync_use_greeting() == "Hello, World!"


async def test_inject_single_dependency_from_async_function_provider():
    context = Context()

    @context.provides
    async def provide_greeting() -> Greeting:
        return Greeting("Hello")

    with context:
        assert await async_use_greeting() == "Hello, World!"


def test_inject_single_dependency_from_sync_generator_provider():
    context = Context()

    did_cleanup = False

    @context.provides
    def provide_greeting() -> Iterator[Greeting]:
        try:
            yield Greeting("Hello")
        finally:
            nonlocal did_cleanup
            did_cleanup = True

    with context:
        assert not did_cleanup
        assert sync_use_greeting() == "Hello, World!"
        assert did_cleanup


async def test_inject_single_dependency_from_async_generator_provider():
    context = Context()

    did_cleanup = False

    @context.provides
    async def provide_greeting() -> AsyncIterator[Greeting]:
        try:
            yield Greeting("Hello")
        finally:
            nonlocal did_cleanup
            did_cleanup = True

    with context:
        assert not did_cleanup
        assert await async_use_greeting() == "Hello, World!"
        assert did_cleanup


def test_inject_single_dependency_from_sync_context_manager_provider():
    context = Context()

    did_cleanup = False

    @context.provides
    class ProvideGreeting:
        def __enter__(self) -> Greeting:
            return Greeting("Hello")

        def __exit__(self, etype, evalue, etrace):
            nonlocal did_cleanup
            did_cleanup = True

    with context:
        assert not did_cleanup
        assert sync_use_greeting() == "Hello, World!"
        assert did_cleanup


async def test_inject_single_dependency_from_async_context_manager_provider():
    context = Context()

    did_cleanup = False

    @context.provides
    class ProvideGreeting:
        async def __aenter__(self) -> Greeting:
            return Greeting("Hello")

        async def __aexit__(self, etype, evalue, etrace):
            nonlocal did_cleanup
            did_cleanup = True

    with context:
        assert not did_cleanup
        assert await async_use_greeting() == "Hello, World!"
        assert did_cleanup


def test_nesting_sync_providers_contexts():
    hello_context = Context()
    good_morning_context = Context()

    @hello_context.provides
    def provide_hello_greeting() -> Greeting:
        return Greeting("Hello")

    @good_morning_context.provides
    def provide_good_morning_greeting() -> Greeting:
        return Greeting("Good morning")

    with hello_context:
        assert sync_use_greeting() == "Hello, World!"
        with good_morning_context:
            assert sync_use_greeting() == "Good morning, World!"
        assert sync_use_greeting() == "Hello, World!"


async def test_nesting_async_providers_contexts():
    hello_context = Context()
    good_morning_context = Context()

    @hello_context.provides
    async def provide_hello_greeting() -> Greeting:
        return Greeting("Hello")

    @good_morning_context.provides
    async def provide_good_morning_greeting() -> Greeting:
        return Greeting("Good morning")

    with hello_context:
        assert await async_use_greeting() == "Hello, World!"
        with good_morning_context:
            assert await async_use_greeting() == "Good morning, World!"
        assert await async_use_greeting() == "Hello, World!"


def test_sync_provider_with_sync_dependency():
    context = Context()

    @context.provides
    def provide_greeting() -> Greeting:
        return Greeting("Hello")

    @context.provides
    def provide_message(*, greeting: Greeting = inject.ed) -> Message:
        return Message(f"{greeting}, World!")

    with context:
        assert sync_use_message() == "Hello, World!"


async def test_sync_provider_with_async_dependency_used_in_async_function():
    context = Context()

    @context.provides
    async def provide_greeting() -> Greeting:
        return Greeting("Hello")

    @context.provides
    def provide_message(*, greeting: Greeting = inject.ed) -> Message:
        return Message(f"{greeting}, World!")

    with context:
        assert await async_use_message() == "Hello, World!"


def test_sync_provider_with_async_dependency_used_in_sync_function():
    context = Context()

    @context.provides
    async def provide_greeting() -> Greeting: ...

    @context.provides
    def provide_message(*, _: Greeting = inject.ed) -> Message: ...

    with context:
        with pytest.raises(RuntimeError, match=r"Cannot use an async provider .* in a sync context"):
            sync_use_message()


async def test_async_provider_with_sync_dependency_used_in_async_function():
    context = Context()

    @context.provides
    def provide_greeting() -> Greeting:
        return Greeting("Hello")

    @context.provides
    async def provide_message(*, greeting: Greeting = inject.ed) -> Message:
        return Message(f"{greeting}, World!")

    with context:
        assert await async_use_message() == "Hello, World!"


def test_reuse_sync_provider():
    context = Context()

    @context.provides
    def provide_greeting() -> Greeting:
        return Greeting("Hello")

    @inject
    def use_greeting(*, greeting: Greeting = inject.ed):
        return greeting

    @inject
    def use_greeting_again(*, greeting: Greeting = inject.ed):
        return f"{greeting} {use_greeting()}"

    with context:
        assert use_greeting_again() == "Hello Hello"
        assert use_greeting() == Greeting("Hello")


async def test_reuse_async_provider():
    context = Context()

    @context.provides
    async def provide_greeting() -> Greeting:
        return Greeting("Hello")

    @inject
    async def use_greeting(*, greeting: Greeting = inject.ed):
        return greeting

    @inject
    async def use_greeting_again(*, greeting: Greeting = inject.ed):
        return f"{greeting} {await use_greeting()}"

    with context:
        assert await use_greeting_again() == "Hello Hello"
        assert await use_greeting() == Greeting("Hello")


def test_error_if_register_provider_for_same_dependency():
    context = Context()

    @context.provides
    def provide_greeting() -> Greeting: ...

    with pytest.raises(TypeError, match=r"Providers already defined for"):

        @context.provides
        def provide_greeting_again() -> Greeting:  # nocov
            ...


def test_unsupported_provider_type():
    context = Context()

    with pytest.raises(TypeError, match="Unsupported provider type"):

        @context.provides
        class NotContextManager:
            pass

    class NotValidProvider:
        def __call__(self): ...

    with pytest.raises(TypeError, match="Unsupported provider type"):
        context.provides(cls=Greeting)(NotValidProvider())  # type: ignore[reportArgumentType]


def test_provider_not_called_if_dependency_provided_explicitely():
    context = Context()

    @context.provides
    def not_implemented() -> Greeting: ...

    with context:
        assert sync_use_greeting(greeting=Greeting("Hello")) == "Hello, World!"


async def test_inject_handles_exits_if_error_in_provider_for_each_injected_function_type():
    context = Context()
    exit_called = False
    expected_error_message = "An expected error"

    @context.provides
    def provide_greeting() -> Iterator[Greeting]:
        try:
            yield Greeting("Hello")
        finally:
            nonlocal exit_called
            exit_called = True

    @inject
    def sync_func_raises_expected_error(*, _: Greeting = inject.ed):
        raise RuntimeError(expected_error_message)

    with pytest.raises(RuntimeError, match=expected_error_message):
        with context:
            sync_func_raises_expected_error()

    assert exit_called
    exit_called = False

    @inject
    async def async_func_raises_expected_error(*, _: Greeting = inject.ed):
        raise RuntimeError(expected_error_message)

    with pytest.raises(RuntimeError, match=expected_error_message):
        with context:
            await async_func_raises_expected_error()

    assert exit_called
    exit_called = False

    @inject
    def sync_gen_raises_expected_error(*, _: Greeting = inject.ed):
        yield
        raise RuntimeError(expected_error_message)

    with pytest.raises(RuntimeError, match=expected_error_message):
        with context:
            list(sync_gen_raises_expected_error())

    assert exit_called
    exit_called = False

    @inject
    async def async_gen_raises_expected_error(*, _: Greeting = inject.ed):
        yield
        raise RuntimeError(expected_error_message)

    with pytest.raises(RuntimeError, match=expected_error_message):
        with context:
            async for _ in async_gen_raises_expected_error():
                pass

    assert exit_called
    exit_called = False


async def test_concurrently_provide_many_dependencies_from_tuple():
    context = Context()

    async def get_greeting():
        return Greeting("Hello")

    async def get_recipient():
        return Recipient("World")

    @context.provides
    async def provide_message_content() -> MessageContent:
        greeting, recipient = await asyncio.gather(get_greeting(), get_recipient())
        return greeting, recipient

    with context:
        assert await async_use_message_content_parts() == "Hello, World!"
        assert await async_use_greeting() == "Hello, World!"


def test_sync_provide_many_dependencies_from_tuple():
    context = Context()

    @context.provides
    def provide_message_content() -> MessageContent:
        return Greeting("Hello"), Recipient("World")

    with context:
        assert sync_use_message_content_parts() == "Hello, World!"
        assert sync_use_greeting() == "Hello, World!"


def test_context_repr():
    context = Context()

    @context.provides
    def provide_greeting() -> Greeting: ...

    @context.provides
    def provide_recipient() -> Recipient: ...

    assert repr(context) == f"Context({Greeting!r}, {Recipient!r})"


def test_error_if_no_return_type_annotation():
    context = Context()

    with pytest.raises(TypeError, match="Cannot determine return type"):

        @context.provides
        def provide_greeting(): ...


def test_cannot_inject_class():
    with pytest.raises(TypeError, match="Unsupported function type"):

        @inject
        class MyClass:
            def __init__(self, *, greeting: Greeting = inject.ed): ...


def test_let_dependency_equal_value():
    with let(Greeting, "Hello"):
        assert sync_use_greeting() == "Hello, World!"


def test_let_message_content_equal_value():
    with let(MessageContent, (Greeting("Hello"), Recipient("World"))):
        assert sync_use_message_content_parts() == "Hello, World!"


def test_on_conflict_replace():
    ctx = Context()

    @ctx.provides
    def provide_greeting_hello() -> Greeting:
        raise AssertionError()  # nocov

    @ctx.provides(on_conflict="replace")
    def provide_greeting_hi() -> Greeting:
        return Greeting("Hi")

    with ctx:
        assert sync_use_greeting() == "Hi, World!"


def test_context_copy():
    context = Context()

    @context.provides
    def provide_greeting() -> Greeting:
        return Greeting("Hello")

    @context.provides
    def provide_recipient_world() -> Recipient:
        return Recipient("World")

    copied_context = context.copy()

    @copied_context.provides(on_conflict="replace")
    def provide_recipient_universe() -> Recipient:
        return Recipient("Universe")

    with context:
        assert sync_use_message_content_parts() == "Hello, World!"

    with copied_context:
        assert sync_use_message_content_parts() == "Hello, Universe!"


@dataclass(kw_only=True)
class MessageData:
    greeting: str
    recipient: str


def test_provide_user_defined_class_from_context():
    context = Context()

    @context.provides
    def make_message_data() -> MessageData:
        return MessageData(greeting="Hello", recipient="World")

    @inject
    def use_message_data(*, message_data: MessageData = inject.ed):
        return f"{message_data.greeting}, {message_data.recipient}!"

    with context:
        assert use_message_data() == "Hello, World!"


def test_provide_user_defined_class_with_let():
    with let(MessageData(greeting="Hello", recipient="World")):

        @inject
        def use_message_data(*, message_data: MessageData = inject.ed):
            return f"{message_data.greeting}, {message_data.recipient}!"

        assert use_message_data() == "Hello, World!"


def test_let_invalid_type_arg():
    with pytest.raises(TypeError, match="Expected type"):

        with let(
            lambda _: None,  # nocov
            "Hello",
        ):
            raise AssertionError()  # nocov
