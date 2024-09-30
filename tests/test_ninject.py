from typing import NewType

from ninject import injector
from ninject import provider

Greeting = NewType("Greeting", str)
Recipient = NewType("Recipient", str)
Message = NewType("Message", str)


@provider.function
def sync_make_greeting() -> Greeting:
    return Greeting("Hello")


@provider.function
def sync_make_recipient() -> Recipient:
    return Recipient("World")


@provider.function
def sync_make_greeting_and_recipient() -> tuple[Greeting, Recipient]:
    return Greeting("Hello"), Recipient("World")


@injector.function
def sync_use_greeting_and_recipient(greeting: Greeting, recipient: Recipient) -> str:
    return f"{greeting} {recipient}!"


@provider.coroutine
async def async_make_greeting() -> Greeting:
    return Greeting("Hello")


@provider.coroutine
async def async_make_recipient() -> Recipient:
    return Recipient("World")


@provider.coroutine
async def async_make_greeting_and_recipient() -> tuple[Greeting, Recipient]:
    return Greeting("Hello"), Recipient("World")


@injector.coroutine
async def async_use_greeting_and_recipient(greeting: Greeting, recipient: Recipient) -> str:
    return f"{greeting} {recipient}!"
