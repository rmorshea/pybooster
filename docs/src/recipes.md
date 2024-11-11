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

## Testing

### Testing Providers

### Testing Injected
