# Ninject 🥷

[![PyPI - Version](https://img.shields.io/pypi/v/ninject.svg)](https://pypi.org/project/ninject)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/ninject.svg)](https://pypi.org/project/ninject)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Ninject uses modern Python features to provide a simple and performant dependency
injection framework.

-   [Installation](#installation)
-   [Basic Usage](#basic-usage)
-   [Types of Providers](#types-of-providers)
-   [Providers with Dependencies](#providers-with-dependencies)
-   [Providing Multiple Dependencies](#providing-multiple-dependencies)
-   [Providing Dependencies Concurrently](#providing-dependencies-concurrently)
-   [Mixing Async and Sync Providers](#mixing-async-and-sync-providers)

## Installation

```console
pip install ninject
```

## Basic Usage

First declare a `Dependency` and `inject` it into a dependent function.

```python
from ninject import Dependency, inject

Message = Dependency("Message", str)


@inject
def print_message(*, message: Message = inject.ed):
    print(message)
```

Next, define a `Context` with a function that `provides` the `Dependency`.

```python
from ninject import Context

context = Context()


@context.provides
def provide_message() -> Message:
    return Message("Hello, World!")
```

Finally, establish the `context` and call the function with the `inject.ed` dependency:

```python
with context:
    print_message()
```

The output will be:

```text
Hello, World!
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
from ninject import Dependency, Context

Message = Dependency("Message", str)

context = Context()

# --- Sync Providers -------------------------------------


@context.provides
def sync_function() -> Message:
    return Message("Hello, World!")


@context.provides
def sync_generator() -> Message:
    try:
        yield Message("Hello, World!")
    finally:
        pass


@context.provides
class SyncContextManager:
    def __enter__(self) -> Message:
        return Message("Hello, World!")

    def __exit__(self, *args) -> None:
        pass


# --- Async Providers ------------------------------------


@context.provides
async def async_function() -> Message:
    return Message("Hello, World!")


@context.provides
async def async_generator() -> Message:
    try:
        yield Message("Hello, World!")
    finally:
        pass


@context.provides
class AsyncContextManager:
    async def __aenter__(self) -> Message:
        return Message("Hello, World!")

    async def __aexit__(self, *args) -> None:
        pass
```

## Providers with Dependencies

Providers can have their own dependencies:

```python
from ninject import Context, Dependency, inject

Greeting = Dependency("Greeting", str)
Recipient = Dependency("Recipient", str)
Message = Dependency("Message", str)


@inject
def print_message(*, message: Message = inject.ed):
    print(message)


context = Context()


@context.provides
def provide_greeting() -> Greeting:
    return Greeting("Hello")


@context.provides
def provide_recipient() -> Greeting:
    return Greeting("World")


@context.provides
def provide_message(
    *, greeting: Greeting = inject.ed, recipient: Recipient = inject.ed
) -> Message:
    return Message(f"{greeting}, {recipient}!")


if __name__ == "__main__":
    with context:
        print_message()
```

The output will be:

```text
Hello, World!
```

## Providing Multiple Dependencies

A single provider can supply multiple dependencies:

```python
from ninject import Context, Dependency, inject

Greeting = Dependency("Greeting", str)
Recipient = Dependency("Recipient", str)
MessageContent = tuple[Greeting, Recipient]


@inject
def print_message(*, greeting: Greeting = inject.ed, recipient: Recipient = inject.ed):
    print(f"{greeting}, {recipient}!")


context = Context()


@context.provides
def provide_message_content() -> MessageContent:
    return "Hello", "World"


if __name__ == "__main__":
    with context:
        print_message()
```

You may also depend on `MessageContent` directly:

```python
from ninject import Context, Dependency, inject

Greeting = Dependency("Greeting", str)
Recipient = Dependency("Recipient", str)
MessageContent = tuple[Greeting, Recipient]


@inject
def print_message(*, message_content: MessageContent = inject.ed):  # TypeError!
    greeting = message_content["greeting"]
    recipient = message_content["recipient"]
    print(f"{greeting}, {recipient}!")


context = Context()


@context.provides(MessageContent)
def provide_message_content() -> dict:
    return {"greeting": "Hello", "recipient": "World"}


if __name__ == "__main__":
    with context:
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
from ninject import Context, Dependency, inject

Greeting = Dependency("Greeting", str)
Recipient = Dependency("Recipient", str)
MessageContent = tuple[Greeting, Recipient]

@inject
async def print_message(
    *, greeting: Greeting = inject.ed, recipient: Recipient = inject.ed
):
    print(f"{greeting}, {recipient}!")


context = Context()


async def get_message() -> str:
    return "Hello"


async def get_recipient() -> str:
    return "World"


async def provide_message_content() -> MessageContent:
    return tuple(await asyncio.gather(get_message(), get_recipient()))


if __name__ == "__main__":
    with context:
        asyncio.run(print_message())
```

## Mixing Async and Sync Providers

To mix async and sync providers, the highest order dependent function must be async. So,
in the example below, that highest order dependent async function is `print_message`.
The fact that `print_message` is async is what allows the sync `provide_message`
function to depend on the async `provide_recipient` function:

```python
import asyncio
from ninject import Context, Dependency, inject

Greeting = Dependency("Greeting", str)
Recipient = Dependency("Recipient", str)

context = Context()


@context.provides(Recipient)
async def provide_recipient() -> str:
    return "World"


@context.provides(Message)
def provide_message(*, recipient: Recipient = inject.ed) -> str:
    return f"Hello, {recipient}!"


@inject
async def print_message(*, message: Message = inject.ed):
    print(message)


if __name__ == "__main__":
    with context:
        asyncio.run(print_message())
```

If `print_message` were sync, then the following error would be raised:

```
RuntimeError: Cannot use an async context manager in a sync context
```
