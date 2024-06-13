import asyncio
from typing import AsyncIterator, Iterator, TypedDict

import pytest

from ninject import Context, Dependency, inject

Greeting = Dependency("Greeting", str)
Recipient = Dependency("Recipient", str)
Message = Dependency("Message", str)


class MessageContent(TypedDict):
    greeting: Greeting
    recipient: Recipient
    punctuation: str


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
def sync_use_message_content(*, message_content: MessageContent = inject.ed):
    return f"{message_content['greeting']}, {message_content['recipient']}{message_content['punctuation']}"


@inject
async def async_use_message_content(*, message_content: MessageContent = inject.ed):
    return f"{message_content['greeting']}, {message_content['recipient']}{message_content['punctuation']}"


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
    async def provide_greeting() -> Greeting:
        return Greeting("Hello")

    @context.provides
    def provide_message(*, greeting: Greeting = inject.ed) -> Message:
        return Message(f"{greeting}, World!")

    with context:
        with pytest.raises(RuntimeError):
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


def test_provides_typed_dict():
    context = Context()

    @context.provides
    def provide_my_dict() -> MessageContent:
        return {"greeting": Greeting("Hello"), "recipient": Recipient("World"), "punctuation": "!"}

    with context:
        assert sync_use_message_content() == "Hello, World!"


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
    def provide_greeting() -> Greeting:
        raise NotImplementedError()

    with pytest.raises(RuntimeError):

        @context.provides
        def provide_greeting_again() -> Greeting:  # nocov
            raise NotImplementedError()


def test_unsupported_provider_type():
    context = Context()

    with pytest.raises(TypeError, match="Cannot determine return type"):

        @context.provides
        class NotContextManager:
            pass

    class NotValidProvider:
        def __call__(self):
            raise NotImplementedError()

    with pytest.raises(TypeError, match="Expected a function or class"):
        context.provides(cls=Greeting)(NotValidProvider())


def test_provider_not_called_if_dependency_provided_explicitely():
    context = Context()

    @context.provides
    def not_implemented() -> Greeting:
        raise NotImplementedError()

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


async def test_concurrently_provide_dependencies():
    context = Context()

    async def get_greeting():
        return Greeting("Hello")

    async def get_recipient():
        return Recipient("World")

    async def get_punctuation() -> str:
        return "!"

    @context.provides
    async def provide_message_content() -> MessageContent:
        greeting, recipient, punctuation = await asyncio.gather(get_greeting(), get_recipient(), get_punctuation())
        return {"greeting": greeting, "recipient": recipient, "punctuation": punctuation}

    with context:
        assert await async_use_message_content() == "Hello, World!"
