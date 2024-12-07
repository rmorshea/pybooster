# Recipes

## Side Effects

To create a provider that does not yield a value but which has side effects, create a
subtype of `None` with the `NewType` function from the `typing` module. This new subtype
can then be used as a [dependency](concepts.md#dependencies).

```python
from collections.abc import Iterator
from typing import NewType

from pybooster import injector
from pybooster import provider
from pybooster import required
from pybooster import solved

SwitchOn = NewType("SwitchOn", None)


SWITCH = False


@provider.iterator
def switch_on() -> Iterator[SwitchOn]:
    global SWITCH
    SWITCH = True
    try:
        yield
    finally:
        SWITCH = False


@injector.function
def is_switch_on(*, _: SwitchOn = required) -> bool:
    return SWITCH


with solved(switch_on):
    assert not SWITCH
    assert is_switch_on()
    assert not SWITCH
```

## Singletons

There's a couple different ways to provide singleton dependencies.

### Eager Singletons

The easiest way to declare singleton values is with the
[shared](concepts.md#shared-injector) injector. Functions requiring a dependency
supplied by a shared injector and which are called in its context will use the same
value:

```python
from dataclasses import dataclass

from pybooster import injector
from pybooster import required


@dataclass
class Dataset:
    x: list[float]
    y: list[float]


@injector.function
def get_dataset(*, dataset: Dataset = required) -> Dataset:
    return dataset


with injector.shared((Dataset, Dataset(x=[1, 2, 3], y=[4, 5, 6]))):
    dataset_1 = get_dataset()
    dataset_2 = get_dataset()
    assert dataset_1 is dataset_2
```

### Lazy Singletons

If you want to ensure that a provider function is only called once, and that the value
it returns is shared across all functions requiring it, you can apply the
[`lru_cache`](https://docs.python.org/3/library/functools.html#functools.lru_cache)
decorator. This will cache the result so the same value is returned each time.

!!! note

    You'll need to use a different decorator for async functions. One option
    is [`aiocache`](https://github.com/aio-libs/aiocache).

```python
from dataclasses import dataclass
from functools import lru_cache

from pybooster import injector
from pybooster import provider
from pybooster import required
from pybooster import solved


@dataclass
class Dataset:
    x: list[float]
    y: list[float]


calls = []


@provider.function
@lru_cache
def dataset_provider() -> Dataset:
    calls.append(None)
    return Dataset(x=[1, 2, 3], y=[4, 5, 6])


@injector.function
def get_dataset(*, dataset: Dataset = required) -> Dataset:
    return dataset


with solved(dataset_provider):
    assert not calls
    dataset_1 = get_dataset()
    assert len(calls) == 1
    dataset_2 = get_dataset()
    assert len(calls) == 1
    assert dataset_1 is dataset_2
```

## Calling Providers

Providers can be called directly as normal context managers with no additional effects.

```python
from typing import NewType

from pybooster import provider

TheAnswer = NewType("TheAnswer", int)


@provider.function
def answer_provider() -> TheAnswer:
    return TheAnswer(42)


with answer_provider() as value:
    assert value == 42
```

This makes it possible to compose provider implementations without requiring them as a
dependency. For example, you could create a SQLAlchemy transaction provider by wrapping
a call to the [`session_provider`][pybooster.extra.sqlalchemy.session_provider]:

```python
from collections.abc import Iterator
from typing import NewType

from sqlalchemy.orm import Session

from pybooster import provider
from pybooster.extra.sqlalchemy import session_provider

Transaction = NewType("Transaction", Session)


@provider.iterator
def transaction_provider() -> Iterator[Transaction]:
    with session_provider() as session, session.begin():
        yield session
```

## Type Hint NameError

!!! note

    This should not be an issue in Python 3.14 with [PEP-649](https://peps.python.org/pep-0649).

If you're encountering a `NameError` when PyBooster tries to infer what type is supplied
by a provider or required for an injector this is likely because you're using
`from __future__ import annotations` and the type hint is imported in an
`if TYPE_CHECKING` block. For example, this code raises `NameError`s because the
`Connection` type is not present at runtime:

```python
from __future__ import annotations

from contextlib import suppress
from typing import TYPE_CHECKING

from pybooster import injector
from pybooster import provider
from pybooster import required

if TYPE_CHECKING:
    from sqlite3 import Connection


with suppress(NameError):

    @provider.function
    def connection_provider() -> Connection: ...

    raise AssertionError("This should not be reached")


with suppress(NameError):

    @injector.function
    def query_database(*, conn: Connection = required) -> None: ...

    raise AssertionError("This should not be reached")
```

To fix this, you can move the import outside of the block:

```python
from __future__ import annotations

from sqlite3 import Connection

from pybooster import injector
from pybooster import provider
from pybooster import required


@provider.function
def connection_provider() -> Connection: ...


@injector.function
def query_database(*, conn: Connection = required) -> None: ...
```

However, some linters like [Ruff](https://github.com/astral-sh/ruff) will automatically
move the import back into the block when they discover that the imported value is only
used as a type hint. To work around this, you can ignore the linter errors or use the
types in such a way that your linter understands they are required at runtime. In the
case of Ruff, you'd ignore the following errors:

- [TC001](https://docs.astral.sh/ruff/rules/typing-only-first-party-import/)
- [TC002](https://docs.astral.sh/ruff/rules/typing-only-third-party-import/)
- [TC003](https://docs.astral.sh/ruff/rules/typing-only-standard-library-import/)

To convince the linter that types used by PyBooster are required at runtime, you can
pass them to the `provides` argument of the `provider` decorator or the `requires`
argument of an `injector` or `provider` decorator.

```python
from __future__ import annotations

from sqlite3 import Connection

from pybooster import injector
from pybooster import provider
from pybooster import required


@provider.function(provides=Connection)
def connection_provider() -> Connection: ...


@injector.function(requires=[Connection])
def query_database(*, conn: Connection = required) -> None: ...
```

!!! tip

    Type checkers should still be able to check the return type using the `provides`
    argument so it may not be necessary to annotate it in the function signature.

## Pytest-Asyncio

Under the hood, PyBooster uses `contextvars` to manage the state of providers and
injectors. If you use `pytest-asyncio` to write async tests it's likely you'll run into
[this issue](https://github.com/pytest-dev/pytest-asyncio/issues/127) where context
established in a fixture is not propagated to your tests. As of writing, the solution
is to create a custom event loop policy and task factory as suggested in
[this comment](https://github.com/pytest-dev/pytest-asyncio/issues/127#issuecomment-2062158881):

```python
import asyncio
import contextvars
import functools
import traceback
from pathlib import Path

import pytest


def task_factory(loop, coro, context=None):
    stack = traceback.extract_stack()
    for frame in stack[-2::-1]:
        match Path(frame.filename).parts[-2]:
            case "pytest_asyncio":
                break  # use shared context
            case "asyncio":
                pass
            case _:  # create context copy
                context = None
                break
    return asyncio.Task(coro, loop=loop, context=context)


class CustomEventLoopPolicy(asyncio.DefaultEventLoopPolicy):
    def __init__(self, context) -> None:
        super().__init__()
        self.context = context

    def new_event_loop(self):
        loop = super().new_event_loop()
        loop.set_task_factory(functools.partial(task_factory, context=self.context))
        return loop


@pytest.fixture(scope="session")
def event_loop_policy():
    policy = CustomEventLoopPolicy(contextvars.copy_context())
    yield policy
    policy.get_event_loop().close()
```
