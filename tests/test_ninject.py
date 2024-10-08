from typing import NewType

import pytest
from pybooster import injector
from pybooster import provider
from pybooster import required
from pybooster.types import ProviderMissingError

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

    with greeting.scope(), recipient.scope(), message.scope():
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

    with greeting.scope(), recipient.scope(), message.scope():
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

    with sync_message.scope(), async_message.scope():
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

    with greeting.scope(), message.scope():
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
        pytest.raises(ProviderMissingError, match=r"No sync provider for .*"),
        greeting.scope(),
        message.scope(),
    ):
        await use_message()
