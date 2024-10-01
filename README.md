# Ninject 🥷

[![PyPI - Version](https://img.shields.io/pypi/v/ninject.svg)](https://pypi.org/project/ninject)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/ninject.svg)](https://pypi.org/project/ninject)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Ninject uses modern Python features to provide a simple and performant dependency
injection framework.

-   [Installation](#installation)
-   [Basic Usage](#basic-usage)
-   [Types of Providers](#types-of-providers)
-   [Providing Built-in Types](#providing-built-in-types)
-   [Providers with Dependencies](#providers-with-dependencies)
-   [Providing Multiple Dependencies](#providing-multiple-dependencies)
-   [Providing Dependencies Concurrently](#providing-dependencies-concurrently)
-   [Async and Sync Providers](#async-and-sync-providers)
-   [Overwriting Providers](#overwriting-providers)

## Installation

```console
pip install ninject
```

## Basic Usage

```python
from dataclasses import dataclass

from ninject import injector, provider, required


# Define a type to be used as a dependency

@dataclass
class Config:
    greeting: str
    recipient: str


# Define a provider for the dependency

@provider.function
def hello_world_config() -> Config:
    return Config("Hello", "World")


# Inject the dependency into a function as keyword-only arguments

@injector.function
def make_message(*, config: Config = required) -> str:
    return f"{config.greeting}, {config.recipient}!"


# Run the function within the context of the provider

with hello_world_config.provide():
    assert make_message() == "Hello, World!"
```

## Types of Providers

A typical provider function is one of the following

-   A function that returns a value
-   A generator that yields a single value
-   An async function that returns a value
-   An async generator that yields a single value

```python
@provider.function
def sync_function() -> ...:
    return ...


@provider.iterator
def sync_generator() -> ...:
    try:
        yield ...
    finally:
        pass


@provider.asyncfunction
async def async_function() -> ...:
    return ...


@provider.asynciterator
async def async_generator() -> ...:
    try:
        yield ...
    finally:
        pass
```

# Singleton Providers

By default, providers are re-evaluated each time a value is injected into a function. To
avoid this you need to make the provider with the `singleton=True` flag **and** ensure
that you use an `entrypoint` to initialize your singleton providers at the start of your
program:

```python
from typing import NewType

from ninject import injector, provider, required, entrypoint

Greeting = NewType("Greeting", str)


COUNT = 0

@provider.function(singleton=True)
def single_greeting() -> Greeting:
    global COUNT
    COUNT += 1
    hellos = ["Hello"] * COUNT
    return Greeting(f"{', '.join(hellos)}!")


@injector.function
def make_message(*, greeting: Greeting = required) -> str:
    return f"{greeting} World!"


@entrypoint.function
def main():
    assert make_message() == "Hello, World!"
    assert make_message() == "Hello, World!"


with single_greeting.provide():
    main()
```

Entrpoints can be declared via a decorator or by creating an `entrypoint.context()`:

```python
with single_greeting.provide(), entrypoint.context():
    assert make_message() == "Hello, World!"
    assert make_message() == "Hello, World!"
```

For async code, you can use the `entrypoint.asyncfunction` or
`async with entrypoint.context()` counterparts. These will both initialize async as well
as sync singleton providers.

## Providing Built-in Types

It's important to provide easily distinguishable types. In the case of built-in objects,
you can leverage `NewType` to define a new class that can serve as a dependency. In the
example below, `Greeting` and `Recipient` are both `str` subtypes that Ninject
recognizes as being distinct:

```python
from typing import NewType

from ninject import injector, provider, required

Greeting = NewType("Greeting", str)
Recipient = NewType("Recipient", str)


@provider.function
def hello_greeting() -> Greeting:
    return Greeting("Hello")


@provider.function
def world_recipient() -> Recipient:
    return Recipient("World")


@injector.function
def make_message(*, greeting: Greeting = required, recipient: Recipient = required) -> str:
    return f"{greeting}, {recipient}!"


with hello_greeting.provide(), world_recipient.provide():
    assert make_message() == "Hello, World!"
```

## Providers with Dependencies

Providers can have their own dependencies:

```python
from typing import NewType
from dataclasses import dataclass

from ninject import injector, provider, required


@dataclass
class Config:
    greeting: str
    recipient: str


Message = NewType("Message", str)


@provider.function
def hello_world_config() -> Config:
    return Config("Hello", "World")


@provider.function
def message_from_config(*, config: Config = required) -> Message:
    return Message(f"{config.greeting}, {config.recipient}!")


@injector.function
def make_long_message(*, message: Message = required) -> str:
    return f"{message} How are you doing today?"


with hello_world_config.provide(), message_from_config.provide():
    assert make_long_message() == "Hello, World! How are you doing today?"
```

## Providing Multiple Dependencies

A single provider can supply multiple dependencies by returning a tuple:

```python
from typing import NewType

from ninject import injector, provider, required

Greeting = NewType("Greeting", str)
Recipient = NewType("Recipient", str)
MessageContent = tuple[Greeting, Recipient]


@provider.function
def hello_world_message_content() -> MessageContent:
    return "Hello", "World"


@injector.function
def make_message(*, greeting: Greeting = required, recipient: Recipient = required):
    return f"{greeting}, {recipient}!"


with hello_world_message_content.provide():
    assert make_message() == "Hello, World!"
```

You may also depend on the tuple, in this case `MessageContent`, directly:

```python
from typing import NewType

from ninject import injector, provider, required

Greeting = NewType("Greeting", str)
Recipient = NewType("Recipient", str)
MessageContent = tuple[Greeting, Recipient]


@provider.function
def hello_world_message_content() -> MessageContent:
    return "Hello", "World"


@injector.function
def make_message(*, message_content: MessageContent = required):  # TypeError!
    greeting, recipient = message_content
    return f"{greeting}, {recipient}!"


if __name__ == "__main__":
    with hello_world_message_content.provide():
        make_message()
```

## Providing Dependencies Concurrently

Ninject does not execute async providers concurrently since doing so can add overhead to
async function calls if it's unnecessary. If you want to satisfy dependencies
concurrently you can leverage the ability to provide
[multiple dependencies](#providing-multiple-dependencies) at once. With that in mind,
you can use `asyncio.gather` to run several async functions concurrently before
returning the dependencies:

```python
import asyncio
from typing import NewType
from ninject import injector, provider, required

Greeting = NewType("Greeting", str)
Recipient = NewType("Recipient", str)
MessageContent = tuple[Greeting, Recipient]


async def get_message() -> str:
    ...  # Some async operation
    return "Hello"


async def get_recipient() -> str:
    ...  # Some async operation
    return "World"


@provider.asyncfunction
async def message_content() -> MessageContent:
    return tuple(await asyncio.gather(get_message(), get_recipient()))


@injector.asyncfunction
async def make_message(*, greeting: Greeting = required, recipient: Recipient = required):
    return f"{greeting}, {recipient}!"


with message_content.provide():
    assert asyncio.run(print_message()) == "Hello, World!"
```

## Async and Sync Providers

Sync and async providers cannot be used together. However you can declare both sync and
async providers for the same dependency which will not overwrite eachother if activated
together:

```python
import asyncio
from typing import NewType

from ninject import injector, provider, required


Greeting = NewType("Greeting", str)


@provider.function
def sync_provider() -> Greeting:
    return Greeting("Synchronous hello")


@provider.asyncfunction
async def async_provider() -> Greeting:
    return Greeting("Asynchronous hello")


@injector.function
def make_sync_message(*, greeting: Greeting = required):
    return f"{greeting} to you!"


@injector.asyncfunction
async def make_async_message(*, greeting: Greeting = required):
    return f"{greeting} to you!"


with sync_provider.provide(), async_provider.provide():
    assert make_sync_message() == "Synchronous hello to you!"
    assert asyncio.run(make_async_message()) == "Asynchronous hello to you!"
```

## Overwriting Providers

You can overwrite providers by activating more than one for the same dependency.

```python
from typing import NewType, Sequence

MessageParts = NewType("MessageParts", Sequence[str])


@provider.function
def init_message_parts() -> MessageParts:
    return MessageParts([])

@provider.function
def add_hello_message_part(*, message_parts: MessageParts = required) -> MessageParts:
    return MessageParts([*message_parts, "Hello"])


@provider.function
def add_world_message_part(*, message_parts: MessageParts = required) -> MessageParts:
    return MessageParts([*message_parts, "World"])


@injector.function
def make_message(*, message_parts: MessageParts = required) -> str:
    return f"{' '.join(message_parts)}!"


with (
    init_message_parts.provide(),
    add_hello_message_part.provide(),
    add_world_message_part.provide(),
):
    assert make_message() == "Hello World!"
```

The order in which providers are activated matters. If you activate
`add_world_message_part` before `add_hello_message_part`, the message will be
`"World Hello!"`. Additionally, if you activated `init_message_parts` after
`add_hello_message_part` and `add_world_message_part`, you would get an error since the
latter two providers depend on `MessageParts` existing already.

## Lower-level Usage

If necessary you can access the current value of a dependency without injecting it into
a function by using the `current` context manager:

```python
from typing import NewType

from ninject import provider, current


Message = NewType("Message", str)


@provider.function
def hello_world_message() -> Message:
    return Message("Hello, World!")


with hello_world_message.provide():
    with current(Message) as message:
        assert message == "Hello, World!"
```

You can also use `current` to set the value of a dependency:

```python
from typing import NewType

from ninject import provider, current

Message = NewType("Message", str)


with current(Message, provide="Hello, World!"):
    with current(Message) as message:
        assert message == "Hello, World!"
```

This can be used to support dependency innjection into class-based context managers
since that cannot be easily done with the built-in `injector` decorators:

```python
from typing import NewType

from ninject import provider, current


Message = NewType("Message", str)


@provider.function
def hello_world_message() -> Message:
    return Message("Hello, World!")


class UseMessage:

    def __init__(self, *, message: Message | None = None):
        self._given_message = message

    def __enter__(self):
        if self._given_message is not None:
            return self._given_message
        self._current_message = current(Message)
        return self._current_message.__enter__()

    def __exit__(self, *args):
        if hasattr(self, "_current_message"):
            try:
                return self._current_message.__exit__(*args)
            finally:
                del self._current_message


with hello_world_message.provide():
    with UseMessage() as message:
        assert message == "Hello, World!"
```
