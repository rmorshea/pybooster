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
