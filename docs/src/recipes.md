# Recipes

## Side Effects

To create a provider that does not yield a value but which has side effects create a
subtype of `None` with the `NewType` function from the `typing` module. This new subtype
can then be used as a [dependency](concepts.md#dependencies).

```python
from typing import Iterator
from typing import NewType

from pybooster import injector
from pybooster import provider
from pybooster import required
from pybooster import solution

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


with solution(switch_on):
    assert not SWITCH
    assert is_switch_on()
    assert not SWITCH
```

## Calling Providers Directly

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

This can allow you to compose provider implementations without requiring them as a
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

## Testing Injected Functions

## Testing Providers

```

```
