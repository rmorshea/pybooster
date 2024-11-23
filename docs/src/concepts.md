# Concepts

## Solutions

In order to [inject](#injectors) a set of [dependencies](#dependencies) PyBooster must
resolve the execution order of their [providers](#providers). That execution order is
determined by performing a topological sort on the dependency graph that gets saved as a
"solution". You can declare one using the [`solved`][pybooster.core.solution.solved]
context manager.

```python
from typing import NewType

from pybooster import injector
from pybooster import provider
from pybooster import required
from pybooster import solved

Recipient = NewType("Recipient", str)


@provider.function
def alice_provider() -> Recipient:
    return Recipient("Alice")


@injector.function
def get_message(*, recipient: Recipient = required) -> str:
    return f"Hello, {recipient}!"


with solved(alice_provider):
    # alice is available to inject as a recipient
    assert get_message() == "Hello, Alice!"
```

!!! tip

    To avoid performance overhead you should try to establish a solution once at the
    beginning of your program.

### Nesting Solutions

You can override a dependency's provider by declaring a new solution for it:

```python
from typing import NewType

from pybooster import injector
from pybooster import provider
from pybooster import required
from pybooster import solved

Recipient = NewType("Recipient", str)


@provider.function
def alice_provider() -> Recipient:
    return Recipient("Alice")


@provider.function
def bob_provider() -> Recipient:
    return Recipient("Bob")


@injector.function
def get_recipient(*, recipient: Recipient = required) -> str:
    return recipient


with solved(alice_provider):
    assert get_recipient() == "Alice"
    with solved(bob_provider):
        assert get_recipient() == "Bob"
    assert get_recipient() == "Alice"
```

## Injectors

Injectors are used to supply a set of dependencies to a function.

### Decorator Injectors

PyBooster supplies a set of decorators that can be added to functions in order to inject
[dependencies](#dependencies) into them. Dependencies for a decorated function are
declared as keyword-only arguments with a type annotation and a default value of
`required`.

```python
from typing import NewType

from pybooster import injector
from pybooster import required

Recipient = NewType("Recipient", str)


@injector.function
def get_message(*, recipient: Recipient = required) -> str:
    return f"Hello, {recipient}!"
```

!!! warning

    Don't forget to add the `required` default value. Without it, PyBooster will not
    know that the argument is a dependency that needs to be injected.

In order for a value to be injected you'll need to solve the depen

```python
from typing import NewType

from pybooster import injector
from pybooster import provider
from pybooster import required
from pybooster import solved

Recipient = NewType("Recipient", str)


@provider.function
def recipient_provider() -> Recipient:
    return Recipient("Alice")


@injector.function
def get_message(*, recipient: Recipient = required) -> str:
    return f"Hello, {recipient}!"


with solved(recipient_provider):
    assert get_message() == "Hello, Alice!"
```

PyBooster supports decorators for the following types of functions or methods:

- [`injector.function`][pybooster.core.injector.function]
- [`injector.iterator`][pybooster.core.injector.iterator]
- [`injector.contextmanager`][pybooster.core.injector.contextmanager]
- [`injector.asyncfunction`][pybooster.core.injector.asyncfunction]
- [`injector.asynciterator`][pybooster.core.injector.asynciterator]
- [`injector.asynccontextmanager`][pybooster.core.injector.asynccontextmanager]

#### Sharing Parameters

You can declare that injected parameter should be shared for the duration of a function
call by setting `shared=True` in the decorator:

```python
from typing import NewType

from pybooster import injector
from pybooster import provider
from pybooster import required
from pybooster import solved

Recipient = NewType("Recipient", str)


@provider.function
def recipient_provider() -> Recipient:
    return Recipient("Alice")


@injector.function
def get_current_values(*, _: Recipient = required) -> injector.CurrentValues:
    return injector.current_values()


@injector.function(shared=True)
def get_current_values_with_shared(*, _: Recipient = required) -> injector.CurrentValues:
    return injector.current_values()


with solved(recipient_provider):
    assert get_current_values() == {}
    assert get_current_values_with_shared() == {Recipient: "Alice"}
```

Setting `shared=True` is effectively equivalent to wrapping function calls in the
[`shared`][pybooster.core.injector.shared] context manager. Doing this might be useful
when dealing with database connections or other resources that should be shared across
multiple functions.

#### Overriding Parameters

You can pass values to a required parameter of a function with an
[injector decorator](#decorator-injectors). The value will be passed as-is to the
function and be used when other providers are called to fulfill the function's remaining
dependencies:

```python
from dataclasses import dataclass
from typing import NewType

from pybooster import injector
from pybooster import provider
from pybooster import required
from pybooster import solved

UserId = NewType("UserId", int)


@dataclass
class Profile:
    name: str
    bio: str


DB = {
    1: Profile(name="Alice", bio="Alice's bio"),
    2: Profile(name="Bob", bio="Bob's bio"),
}


@provider.function
def user_id_provider() -> UserId:
    return UserId(1)


@provider.function
def profile_provider(*, user_id: UserId = required) -> Profile:
    return DB[user_id]


@injector.function
def get_profile_summary(*, user_id: UserId = required, profile: Profile = required) -> str:
    return f"#{user_id} {profile.name}: {profile.bio}"


with solved(user_id_provider, profile_provider):
    assert get_profile_summary() == "#1 Alice: Alice's bio"
    assert get_profile_summary(user_id=UserId(2)) == "#2 Bob: Bob's bio"
```

### Shared Injector

You can declare that a set of dependency should be shared across all usages for the
duration of a context using the [`shared`][pybooster.core.injector.shared] context
manager. The `shared` context manager will also yield the current values for those
dependencies:

```python
from dataclasses import dataclass

from pybooster import injector
from pybooster import provider
from pybooster import required
from pybooster import solved


@dataclass
class Auth:
    username: str
    password: str


@provider.function
def auth() -> Auth:
    return Auth(username="alice", password="EGwVEo3y9E")


@injector.function
def get_auth(*, auth: Auth = required) -> Auth:
    return auth


with solved(auth):
    assert get_auth() is not get_auth()
    with injector.shared(Auth) as values:
        assert values[Auth] is get_auth()
        assert get_auth() is get_auth()
```

You can, instead or additionally, override the current values for a dependencies by
passing a mapping of dependency types to desired values under the `values` keyword:

```python
from dataclasses import dataclass
from typing import NewType

from pybooster import injector
from pybooster import provider
from pybooster import required
from pybooster import solved

UserId = NewType("UserId", int)


@dataclass
class Profile:
    name: str
    bio: str


DB = {
    1: Profile(name="Alice", bio="Alice's bio"),
    2: Profile(name="Bob", bio="Bob's bio"),
}


@provider.function
def user_id_provider() -> UserId:
    return UserId(1)


@provider.function
def profile_provider(*, user_id: UserId = required) -> Profile:
    return DB[user_id]


@injector.function
def get_profile_summary(*, user_id: UserId = required, profile: Profile = required) -> str:
    return f"#{user_id} {profile.name}: {profile.bio}"


with solved(user_id_provider, profile_provider):
    assert get_profile_summary() == "#1 Alice: Alice's bio"
    with injector.shared((UserId, 2)):
        assert get_profile_summary() == "#2 Bob: Bob's bio"
```

### Current Values

You can access a mapping of the current values for all dependencies by calling the
[`current_values`][pybooster.core.injector.current_values] function. This can be useful
for debugging:

```python
from typing import NewType

from pybooster import injector

UserId = NewType("UserId", int)


assert injector.current_values() == {}
with injector.shared((UserId, 1)):
    assert injector.current_values() == {UserId: 1}
```

## Providers

A provider is a function that creates or yields a [dependency](#dependencies). What
providers are available for, and thus what dependencies can be [injected](#injectors)
are determined by whether they were included in the current [solution](#solutions).

### Sync Providers

Sync providers can either be functions the return a dependency's value:

```python
from dataclasses import dataclass

from pybooster import provider


@dataclass
class Config:
    app_name: str
    app_version: int
    debug_mode: bool


@provider.function
def config_provider() -> Config:
    return Config(app_name="MyApp", app_version=1, debug_mode=True)
```

Or iterators that yield the dependency's value. Iterators are useful when you have
resources that need to be cleaned up when the dependency's value is no longer in use.

```python
import sqlite3
from collections.abc import Iterator

from pybooster import provider


@provider.iterator
def sqlite_connection() -> Iterator[sqlite3.Connection]:
    with sqlite3.connect("example.db") as conn:
        yield conn
```

### Async Providers

Async providers can either be a coroutine function that returns a dependency's value:

```python
from asyncio import sleep
from dataclasses import dataclass

from pybooster import provider


@dataclass
class Config:
    app_name: str
    app_version: int
    debug_mode: bool


@provider.asyncfunction
async def async_config_provider() -> Config:
    await sleep(1)  # Do some async work here...
    return Config(app_name="MyApp", app_version=1, debug_mode=True)
```

Or async iterators that yield the dependency's value. Async iterators are useful when
you have resources that need to be cleaned up when the dependency's value is no longer
in use.

```python
from asyncio import StreamReader
from asyncio import open_connection
from collections.abc import AsyncIterator

from pybooster import provider


@provider.asynciterator
async def example_reader() -> AsyncIterator[StreamReader]:
    reader, writer = await open_connection("example.com", 80)
    writer.write(b"GET / HTTP/1.1\r\nHost: example.com\r\n\r\n")
    await writer.drain()
    try:
        yield reader
    finally:
        writer.close()
        await writer.wait_closed()
```

Async providers are executed concurrently where possible in the current
[solution](#solutions).

### Generic Providers

A single provider can supply multiple types of dependencies if it provides a base class,
union, `Any`, or includes a `TypeVar` which is narrowed later. To narrow the type before
using it in a solution you can use the `[]` syntax to annotate the concrete type that
the provider will supply when solving. So, in the case you have a provider that loads
json data from a file you could annotate its return type as `Any` but narrow the type to
`ConfigDict` before declaring a solution:

```python
import json
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any
from typing import TypedDict

from pybooster import injector
from pybooster import provider
from pybooster import required
from pybooster import solved


@provider.function
def json_provider(path: Path) -> Any:
    with path.open() as f:
        return json.load(f)


class ConfigDict(TypedDict):
    app_name: str
    app_version: int
    debug_mode: bool


@injector.function
def get_config(*, config: ConfigDict = required) -> ConfigDict:
    return config


tempfile = NamedTemporaryFile()
json_file = Path(tempfile.name)
json_file.write_text('{"app_name": "MyApp", "app_version": 1, "debug_mode": true}')

with solved(json_provider[ConfigDict].bind(json_file)):
    assert get_config() == {
        "app_name": "MyApp",
        "app_version": 1,
        "debug_mode": True,
    }
```

Since concrete types for `TypeVar`s cannot be automatically inferred from the arguments
passed to the provider. You must always narrow the return type (as shown above) or pass
a `provides` inference function to the `@provider` decorator to specify how to figure
out the concrete type. This function should take all the non-dependency arguments of the
provider and return the concrete type. In the example below the provider is generic on
the `cls: type[T]` argument so the `provides` inference function will just return that:

```python
import json
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import TypeVar

from pybooster import injector
from pybooster import provider
from pybooster import required
from pybooster import solved


@dataclass
class Config:
    app_name: str
    app_version: int
    debug_mode: bool


@dataclass
class Auth:
    username: str
    password: str


T = TypeVar("T")


@provider.function(provides=lambda cls, *a, **kw: cls)
def config_file_provider(cls: type[T], path: str | Path) -> T:
    with Path(path).open() as f:
        return cls(**json.load(f))


@injector.function
def get_config(*, config: Config = required) -> Config:
    return config


tempfile = NamedTemporaryFile()
json_file = Path(tempfile.name)
json_file.write_text('{"app_name": "MyApp", "app_version": 1, "debug_mode": true}')

with solved(config_file_provider.bind(Config, json_file)):
    assert get_config() == Config(app_name="MyApp", app_version=1, debug_mode=True)
```

!!! tip

    This approach also works great for a provider that has `overload` implementations.

### Binding Parameters

You can pass additional arguments to a provider by adding parameters to a provider
function signature that are not [dependencies](#dependencies):

```python
import sqlite3
from collections.abc import Iterator
from sqlite3 import Connection

from pybooster import provider


@provider.iterator
def sqlite_connection(database: str) -> Iterator[Connection]:
    with sqlite3.connect(database) as conn:
        yield conn
```

These parameters can be supplied when solving using the `bind` method:

```python { test="false"}
with solved(sqlite_connection.bind(":memory:")):
    ...
```

!!! note

    Bindable parameters are not allowed to be dependencies.

### Mixing Sync/Async

You can define both sync and async providers for the same dependency. When running in an
async context, PyBooster will prefer async providers over sync providers.

```python
import asyncio
from dataclasses import dataclass

from pybooster import injector
from pybooster import provider
from pybooster import required
from pybooster import solved


@dataclass
class Auth:
    username: str
    password: str


@provider.function
def sync_auth_provider() -> Auth:
    return Auth(username="sync-user", password="sync-pass")


@provider.asyncfunction
async def async_auth_provider() -> Auth:
    await asyncio.sleep(0)  # Do some async work here...
    return Auth(username="async-user", password="async-pass")


@injector.function
def sync_get_auth(*, auth: Auth = required) -> str:
    return f"{auth.username}:{auth.password}"


@injector.asyncfunction
async def async_get_auth(*, auth: Auth = required) -> str:
    return f"{auth.username}:{auth.password}"


with solved(sync_auth_provider, async_auth_provider):
    assert sync_get_auth() == "sync-user:sync-pass"
    assert asyncio.run(async_get_auth()) == "async-user:async-pass"
```

## Dependencies

A dependency is (almost) any Python type or class required by a function.

### Built-In Types

PyBooster does not allow you to use built-in types directly. Instead you should use
[`NewType`](https://docs.python.org/3/library/typing.html#newtype) to define a distinct
subtype so that it is easily identifiable. For example, instead of using `str` to
represent a username, you might define a `Username` new type like this:

```python
from typing import NewType

Username = NewType("Username", str)
```

Now you can make a [provider](#providers) for `Username` and inject it into functions.

```python
from typing import NewType

from pybooster import injector
from pybooster import provider
from pybooster import required
from pybooster import solved

Username = NewType("Username", str)


@provider.function
def username_provider() -> Username:
    return "alice"


@injector.function
def get_message(*, username: Username = required) -> str:
    return f"Hello, {username}!"


with solved(username_provider):
    assert get_message() == "Hello, alice!"
```

### User-Defined Types

This includes types you or a third-party package define. In this case, an `Auth` class:

```python
from dataclasses import dataclass

from pybooster import injector
from pybooster import provider
from pybooster import required
from pybooster import solved


@dataclass
class Auth:
    role: str
    username: str
    password: str


@provider.function
def auth_provider() -> Auth:
    return Auth(role="user", username="alice", password="EGwVEo3y9E")


@injector.function
def get_login_message(*, auth: Auth = required) -> str:
    return f"Logged in as {auth.username}"


with solved(auth_provider):
    assert get_login_message() == "Logged in as alice"
```

### Tuple Types

You can provide a tuple of types from a provider in order to supply multiple
dependencies at once. This can be useful if you need to destructure some value into
separate dependencies.

```python
import json
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import NewType

from pybooster import injector
from pybooster import provider
from pybooster import required
from pybooster import solved

Username = NewType("Username", str)
Password = NewType("Password", str)

tempfile = NamedTemporaryFile()
secrets_json = Path(tempfile.name)
secrets_json.write_text('{"username": "alice", "password": "EGwVEo3y9E"}')


@provider.function
def username_and_password_provider() -> tuple[Username, Password]:
    with secrets_json.open() as f:
        secrets = json.load(f)
    return Username(secrets["username"]), Password(secrets["password"])


@injector.function
def get_login_message(*, username: Username = required) -> str:
    return f"Logged in as {username}"


with solved(username_and_password_provider):
    assert get_login_message() == "Logged in as alice"
```
