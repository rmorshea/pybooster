# Ninject 🥷

[![PyPI - Version](https://img.shields.io/pypi/v/ninject.svg)](https://pypi.org/project/ninject)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/ninject.svg)](https://pypi.org/project/ninject)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Ninject uses modern Python features to provide a simple and performant dependency
injection framework.

-   [Installation](#installation)
-   [Basic Usage](#basic-usage)
-   [Types of Providers](#types-of-providers)
-   [Composing Providers](#composing-providers)
-   [Providing Distinct Types](#providing-distinct-types)
-   [Providing Static Values](#providing-static-values)
-   [Providers with Dependencies](#providers-with-dependencies)
-   [Providing Multiple Dependencies](#providing-multiple-dependencies)
-   [Providing Dependencies Concurrently](#providing-dependencies-concurrently)
-   [Mixing Async and Sync Providers](#mixing-async-and-sync-providers)

## Installation

```console
pip install ninject
```

## Basic Usage

```python
import ninject as n
from dataclasses import dataclass


# Define a type to be used as a dependency

@dataclass
class Config:
    greeting: str
    recipient: str


# Define a provider for the dependency

@n.provider
def provide_config() -> Config:
    return Config("Hello", "World")


# Injec the dependency into a function

@n.inject
def make_message(*, config: Config = n.required) -> str:
    return f"{config.greeting}, {config.recipient}!"


# Run the function with in the context of the provider

with provide_config():
    assert make_message() == "Hello, World!"

    # Or access the dependency directly

    with n.Current(Config) as config:
        assert config == Config("Hello", "World")
```

## Types of Providers

A provider is one of the following

-   A function that returns a value
-   A generator that yields a single value
-   A context manager class that yields a value
-   An async function that returns a value
-   An async generator that yields a single value
-   An async context manager class that yields a value

```python
@n.provider
def sync_function() -> ...:
    return ...


@n.provider
def sync_generator() -> ...:
    try:
        yield ...
    finally:
        pass


@n.provider
class SyncContextManager:
    def __enter__(self) -> ...:
        return ...

    def __exit__(self, *args) -> None:
        pass


@n.provider
async def async_function() -> ...:
    return ...


@n.provider
async def async_generator() -> ...:
    try:
        yield ...
    finally:
        pass


@n.provider
class AsyncContextManager:
    async def __aenter__(self) -> ...:
        return ...

    async def __aexit__(self, *args) -> None:
        pass
```

## Dependencies with Default Values

You allow a dependency to be optional by declaring a `default` instead of `required`:

```python
import ninject as n


@n.inject
def make_message(*, config: Config = n.default[Config("Hello", "World")]) -> str:
    return f"{config.greeting}, {config.recipient}!"


assert make_message() == "Hello, World!"
```

## Composing Providers

You compose providers with `|` so they can be activated together:

```python
from dataclasses import dataclass
import ninject as n


@dataclass
class GreetingConfig:
    greeting: str
    recipient: str


@dataclass
class FarewellConfig:
    farewell: str
    recipient: str


@n.provider
def provide_greeting_config() -> GreetingConfig:
    return GreetingConfig("Hello", "Bob")


@n.provider
def provide_farewell_config() -> FarewellConfig:
    return FarewellConfig("Goodbye", "Bob")


provide_all_configs = provide_greeting_config | provide_farewell_config


@n.inject
def make_message(
    *,
    greeting_config: GreetingConfig = n.required,
    farewell_config: FarewellConfig = n.required,
) -> str:
    greeting_str = f"{greeting_config.greeting}, {greeting_config.recipient}!"
    farewell_str = f"{farewell_config.farewell}, {farewell_config.recipient}!"
    return f"{greeting_str} ... {farewell_str}"


with provide_all_configs():
    assert make_message() == "Hello, Bob! ... Goodbye, Bob!"
```

The last provider in the chain will override any previous providers with the same type.

```python
@n.provider
def provide_bob_greeting_config() -> GreetingConfig:
    return GreetingConfig("Hello", "Bob")


@n.provider
def provide_alice_greeting_config() -> GreetingConfig:
    return GreetingConfig("Hi", "Alice")


provide_greeting_config = provide_bob_greeting_config | provide_alice_greeting_config


with provide_greeting_config:
    with n.Current(GreetingConfig) as config:
        assert config == GreetingConfig("Hi", "Alice")
```

You can also activate them separately in the same `with` statement, but order matters if
your [providers have dependencies](#providers-with-dependencies):

## Providing Built-in Types

It's important to provide easily distinguishable types. In the case of built-in types,
you can use `NewType` to define a new subtype. In the example below, `Greeting` and
`Recipient` are both distinct `str` subtypes recognized by Ninject:

```python
from typing import NewType
import ninject as n

Greeting = NewType("Greeting", str)
Recipient = NewType("Recipient", str)


@n.provider
def provide_greeting() -> Greeting:
    return Greeting("Hello")


@n.provider
def provide_recipient() -> Recipient:
    return Recipient("World")
```

This way, you can use the built-in type as a dependency:

```python
@n.provider
def provide_message(*, greeting: Greeting = inject.ed, recipient: Recipient = inject.ed) -> str:
    return f"{greeting}, {recipient}!"
```

## Providing Static Values

To do this you can use the `let` context:

```python
from dataclasses import dataclass
import ninject as n


@dataclass
class Config:
    greeting: str
    recipient: str


@n.inject
def make_message(*, config: Config = n.required) -> str:
    return f"{config.greeting}, {config.recipient}!"


with n.let(Config(greeting="Hello", recipient="World")):
    assert make_message() == "Hello, World!"
```

When a type alias or `NewType` is used to define a dependency, pass the type and the
value separately:

```python
from typing import NewType
import ninject as n

Greeting = NewType("Greeting", str)
Recipient = NewType("Recipient", str)


@n.inject
def make_message(*, config: Config = n.required) -> str:
    return f"{config.greeting}, {config.recipient}!"


with (
    n.let(Greeting, "Hello"),
    n.let(Recipient, "World"),
):
    assert make_message() == "Hello, World!"
```

## Providers with Dependencies

Providers can have their own dependencies:

```python
from dataclasses import dataclass
from typing import NewType
import ninject as n


@dataclass
class Config:
    greeting: str
    recipient: str


Message = Dependency("Message", str)


@n.provider
def provide_config() -> Greeting:
    return Config("Hello", "World")


@n.provider
def provide_message(*, config: Config = n.required) -> Message:
    return Message(f"{greeting}, {recipient}!")


@n.inject
def print_message(*, message: Message = n.required):
    print(message)


if __name__ == "__main__":
    with provide_config(), provide_message():
        print_message()
```

The output will be:

```text
Hello, World!
```

## Providing Multiple Dependencies

A single provider can supply multiple dependencies by returning a tuple:

```python
from typing import NewType
import ninject as n

Greeting = NewType("Greeting", str)
Recipient = NewType("Recipient", str)
MessageContent = tuple[Greeting, Recipient]


@n.provider
def provide_message_content() -> MessageContent:
    return "Hello", "World"


@n.inject
def print_message(*, greeting: Greeting = inject.ed, recipient: Recipient = inject.ed):
    print(f"{greeting}, {recipient}!")


if __name__ == "__main__":
    with provide_message_content():
        print_message()
```

You may also depend on the tuple, in this case `MessageContent`, directly:

```python
from typing import NewType
import ninject as n

Greeting = NewType("Greeting", str)
Recipient = NewType("Recipient", str)
MessageContent = tuple[Greeting, Recipient]


@n.provider(MessageContent)
def provide_message_content() -> dict:
    return {"greeting": "Hello", "recipient": "World"}


@n.inject
def print_message(*, message_content: MessageContent = inject.ed):  # TypeError!
    greeting, recipient = message_content
    print(f"{greeting}, {recipient}!")



if __name__ == "__main__":
    with provide_message_content():
        print_message()
```

## Providing Dependencies Concurrently

Ninject does not execute async providers concurrently since doing so can add a
substantial amount of overhead to async function calls if it's unnecessary. If you want
to satisfy dependencies concurrently you can leverage the ability to provide
[multiple dependencies](#providing-multiple-dependencies) at once. With that in mind,
you can use `asyncio.gather` to run several async functions concurrently before
returning the dependencies:

```python
import asyncio
from typing import NewType
import ninject as n

Greeting = NewType("Greeting", str)
Recipient = NewType("Recipient", str)
MessageContent = tuple[Greeting, Recipient]


async def get_message() -> str:
    ...  # Some async operation
    return "Hello"


async def get_recipient() -> str:
    ...  # Some async operation
    return "World"


@n.provider
async def provide_message_content() -> MessageContent:
    return tuple(await asyncio.gather(get_message(), get_recipient()))


@n.inject
async def print_message(*, greeting: Greeting = inject.ed, recipient: Recipient = inject.ed):
    print(f"{greeting}, {recipient}!")


if __name__ == "__main__":
    with provide_message_content():
        asyncio.run(print_message())
```

## Mixing Async and Sync Providers

Mixing sync and async providers is allowed so long as they are used in an async context:

```python
import asyncio
from typing import NewType
import ninject as n

Recipient = NewType("Recipient", str)
Message = NewType("Message", str)


@n.provider
async def provide_recipient() -> Recipient:
    return Recipient("World")


@n.provider
def provide_message(*, recipient: Recipient = inject.ed) -> Message:
    return Message(f"Hello, {recipient}!")


@n.inject
async def print_message(*, message: Message = inject.ed):
    print(message)


if __name__ == "__main__":
    with provide_recipient(), provide_message():
        asyncio.run(print_message())
```

If `print_message` were sync, then the following error would be raised:

```
RuntimeError: Cannot use an async context manager in a sync context
```
