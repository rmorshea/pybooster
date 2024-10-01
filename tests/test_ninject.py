from typing import NewType

import pytest

from ninject import injector
from ninject import provider
from ninject import required
from ninject.types import ProviderMissingError

Greeting = NewType("Greeting", str)
Recipient = NewType("Recipient", str)
Message = NewType("Message", str)


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

    with greeting.provide(), recipient.provide(), message.provide():
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

    with greeting.provide(), recipient.provide(), message.provide():
        assert await use_message() == "Hello World"


async def test_sync_and_async_providers_do_not_overwrite_eachother():
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

    with sync_message.provide(), async_message.provide():
        assert use_sync_message() == "Hello, Sync"
        assert await use_async_message() == "World, Async"


def test_can_overwrite_sync_provider():
    @provider.function
    def message() -> Message:
        return Message("Hello")

    @provider.function
    def special_message(*, message: Message = required) -> Message:
        return Message(f"Special {message}")

    @injector.function
    def use_message(*, message: Message = required):
        return message

    with message.provide(), special_message.provide():
        assert use_message() == "Special Hello"


async def test_can_overwrite_async_provider():
    @provider.asyncfunction
    async def message() -> Message:
        return Message("Hello")

    @provider.asyncfunction
    async def special_message(*, message: Message = required) -> Message:
        return Message(f"Special {message}")

    @injector.asyncfunction
    async def use_message(*, message: Message = required):
        return message

    with message.provide(), special_message.provide():
        assert await use_message() == "Special Hello"


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

    with greeting.provide(), message.provide():
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
        pytest.raises(ProviderMissingError, match="Async provider .* cannot be used in a sync context"),
        greeting.provide(),
        message.provide(),
    ):
        await use_message()
