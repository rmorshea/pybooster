# Concepts

## Injectors

Injectors are used to supply a set of dependencies to a function or context.

### Decorator Injectors

PyBooster supplies a set of decorators that can be added to functions in order to inject
[dependencies](#dependencies). Dependencies for a decorated function are declared as
keyword-only arguments with a type annotation and a default value of `required`.

```python
from typing import NewType

from pybooster import injector
from pybooster import required

Recipient = NewType("Recipient", str)


@injector.function
def hello_greeting(*, recipient: Recipient = required) -> str:
    return f"Hello, {recipient}!"
```

!!! warning

    Don't forget to add the `required` default value. Without it, PyBooster will not
    know that the argument is a dependency that needs to be injected.

In order for a value to be injected you'll need to declare a [provider](#providers) and
activate it's [scope](#scoping-providers) before calling the function.

```python
from typing import NewType

from pybooster import injector
from pybooster import provider
from pybooster import required

Recipient = NewType("Recipient", str)


@injector.function
def hello_greeting(*, recipient: Recipient = required) -> str:
    return f"Hello, {recipient}!"


@provider.function
def alice() -> Recipient:
    return Recipient("Alice")


with alice.scope():
    assert hello_greeting() == "Hello, Alice!"
```

PyBooster supports decorators for the following types of functions:

-   `injector.function`
-   `injector.asyncfunction`
-   `injector.iterator`
-   `injector.asynciterator`
-   `injector.contextmanager`
-   `injector.asynccontextmanager`

You can use all of these decorators on methods of a class as well.

!!! tip

    You can always skip injecting a dependency by passing a value directly as an argument:

    ```python { test="false" }
    assert hello_greeting(recipient="Bob") == "Hello, Bob!"
    ```

    This will not trigger the provider for `Recipient` and will use the value passed to the
    function instead. Doing so can be useful for re-using a dependency across multiple function
    calls without the indirection created by establishing a [`shared`](#shared-contexts) context.

### Inline Injector

If you need to access the current value of a dependency outside of a function, you can
use `injector.current` by activating it either as a synchronous or asynchronous context
manager.

```python
from typing import NewType

from pybooster import injector
from pybooster import provider

Recipient = NewType("Recipient", str)


@provider.function
def alice() -> Recipient:
    return Recipient("Alice")


with alice.scope(), injector.current(Recipient) as recipient:
    assert recipient == "Alice"
```

### Shared Context Injector

By default, PyBooster will create a new instance of a dependency each time it is
injected. To change this, using the `shared` context manager to declare that a
dependency should be re-used across all injections for the duration of a context. This
will immediately execute the provider and store the result for future use.

```python
from dataclasses import dataclass

from pybooster import injector
from pybooster import provider
from pybooster import required


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


with auth.scope():

    assert get_auth() is not get_auth()

    with injector.shared(Auth):
        assert get_auth() is get_auth()
```

!!! info

    If the dependency's provider is, or could be asynchronous, enter the `shared()`
    context manager using `async with` instead. This will ensure that async providers
    can be executed successfully. Even if the provider is synchronous, using `async with`
    will still work.

### Shared Value Injector

You can share a static value amongst injections and without needing a provider by
passing a `value` argument to the `shared` context manager. This can be useful for
sharing configuration values or other static data.

```python
from dataclasses import dataclass

from pybooster import injector
from pybooster import required


@dataclass
class Auth:
    username: str
    password: str


@injector.function
def get_auth(*, auth: Auth = required) -> Auth:
    return auth


with injector.shared(Auth, value=Auth(username="alice", password="EGwVEo3y9E")):
    assert get_auth() is get_auth()
```

Using a shared value will also cause any providers for the dependency to be ignored.

```python
import os
from dataclasses import dataclass

from pybooster import injector
from pybooster import provider
from pybooster import required


@dataclass
class Auth:
    username: str
    password: str


@provider.function
def auth_from_env() -> Auth:
    return Auth(username=os.environ["USERNAME"], password=os.environ["PASSWORD"])


@injector.function
def get_auth(*, auth: Auth = required) -> Auth:
    return auth


fake_auth = Auth(username="fake", password="fake")
with injector.shared(Auth, value=fake_auth), auth_from_env.scope():
    assert get_auth() == fake_auth
```

Note that if `auth_from_env` had gotten executed it would have raised a `KeyError`
because `os.environ["USERNAME"]` and `os.environ["PASSWORD"]` would not have been set.
However, because the `shared` context manager was used, the provider was skipped.

## Providers

A provider is a function that creates or yields a [dependency](#dependencies). Providers
are used to define how dependencies resolved when they are [injected](#injectors) into a
function or context. What providers are available depends on what scopes are active when
a dependency is resolved.

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
def config() -> Config:
    return Config(app_name="MyApp", app_version=1, debug_mode=True)
```

Or iterators that yield the dependency's value. Iterators are useful when you have
resources that need to be cleaned up when the dependency's value is no longer in use.

```python
import sqlite3
from typing import Iterator

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
async def async_config() -> Config:
    await sleep(1)  # Do some async work here...
    return Config(app_name="MyApp", app_version=1, debug_mode=True)
```

Or async iterators that yield the dependency's value. Async iterators are useful when
you have resources that need to be cleaned up when the dependency's value is no longer
in use.

```python
from asyncio import StreamReader
from asyncio import open_connection
from typing import AsyncIterator

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

### Generic Providers

You can use a single provider to supply multiple dependencies by narrowing the return
type if it's a base class, union, `Any`, or includes a `TypeVar`. This is done using
square brackets to annotate the exact concrete type that the provider will supply before
activating its [scope](#scoping-providers). So, in the case you have a provider that
loads json data from a file you could annotate its return type as `Any` but narrow the
type to `ConfigDict` before entering its scope.

```python
import json
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any
from typing import TypedDict

from pybooster import injector
from pybooster import provider
from pybooster import required


@provider.function
def load_json(path: str | Path) -> Any:
    with Path(path).open() as f:
        return json.load(f)


class ConfigDict(TypedDict):
    app_name: str
    app_version: int
    debug_mode: bool


@injector.function
def get_config(*, config: ConfigDict = required) -> ConfigDict:
    return config


tempfile = NamedTemporaryFile()
CONFIG_JSON = Path(tempfile.name)
CONFIG_JSON.write_text('{"app_name": "MyApp", "app_version": 1, "debug_mode": true}')

with load_json[ConfigDict].scope(CONFIG_JSON):
    assert get_config() == {"app_name": "MyApp", "app_version": 1, "debug_mode": True}
```

Since concrete types for `TypeVar`s cannot be automatically inferred from the arguments
passed to the provider. You must always narrow the return type (as shown above) or pass
a `provides` inference function to the `@provider` decorator to specify how to figure
out the concrete type. This function should can take all the non-dependency arguments of
the provider and return the concrete type. In the example below the provider is generic
on the `cls: type[T]` argument so the `provides` inference function will just return
that:

```python
from dataclasses import dataclass
from typing import TypeVar
from pathlib import Path
from tempfile import NamedTemporaryFile

from pybooster import injector
from pybooster import provider
from pybooster import required


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
def config_from_file(cls: type[T], path: str | Path) -> T:
    with Path(path).open() as f:
        return cls(**json.load(f))


@injector.function
def get_config(*, config: Config = required) -> Config:
    return config


tempfile = NamedTemporaryFile()
CONFIG_JSON = Path(tempfile.name)
CONFIG_JSON.write_text('{"app_name": "MyApp", "app_version": 1, "debug_mode": true}')

with config_from_file.scope(Config, CONFIG_JSON):
    assert get_config() == Config(app_name="MyApp", app_version=1, debug_mode=True)
```

!!! tip

    This approach also works great for a provider with `overload`s.

### Parameterizing Providers

You can pass additional arguments to a provider by adding parameters to a provider
function signature that are not [dependencies](#dependencies):

```python
import sqlite3
from typing import Iterator

from pybooster import provider


@provider.iterator
def sqlite_connection(database: str) -> Iterator[sqlite3.Connection]:
    with sqlite3.connect(database) as conn:
        yield conn
```

These parameters can be supplied when activating the `scope`.

```python { test="false"}
with sqlite_connection.scope(":memory:"):
    ...
```

You can also declare these parameters as dependencies by making them keyword-only,
annotating them with the desired type, and setting the default value to `required`.

```python
import os
import sqlite3
from typing import Iterator
from typing import NewType

from pybooster import provider
from pybooster import required

Database = NewType("DatabasePath", str)


@provider.function
def sqlite_database() -> Database:
    return Database(os.environ.get("SQLITE_DATABASE", ":memory:"))


@provider.iterator
def sqlite_connection(*, database: Database = required) -> Iterator[sqlite3.Connection]:
    with sqlite3.connect(database) as conn:
        yield conn
```

### Scoping Providers

What providers are available to inject dependencies is determined by what scopes are
active when the dependency is resolved. Scopes can be activated using the `scope` method
of a provider.

```python
from typing import NewType

from pybooster import provider

Recipient = NewType("Recipient", str)


@provider.function
def alice() -> Recipient:
    return Recipient("Alice")


with alice.scope():
    ...  # alice is available to inject
```

You can override a dependency's provider by activating a new scope for the same
dependency.

```python
from typing import NewType

from pybooster import injector
from pybooster import provider
from pybooster import required

Recipient = NewType("Recipient", str)


@provider.function
def alice() -> Recipient:
    return Recipient("Alice")


@provider.function
def bob() -> Recipient:
    return Recipient("Bob")


@injector.function
def get_recipient(*, recipient: Recipient = required) -> str:
    return recipient


with alice.scope():
    assert get_recipient() == "Alice"
    with bob.scope():
        assert get_recipient() == "Bob"
    assert get_recipient() == "Alice"
```

!!! info

    The exact behavior of scopes can depend on whether the requested dependency is
    a [union](#union-types) or has [subclasses](#subclassed-types). Refer to those
    sections for more information.

### Mixing Sync/Async

You can define both sync and async providers for the same dependency. Sync providers can
be used in async contexts, but not the other way around. PyBooster will always choose to
use an async provider when running in an async context and one is available.

```python
import asyncio
from dataclasses import dataclass

from pybooster import injector
from pybooster import provider
from pybooster import required


@dataclass
class Auth:
    username: str
    password: str


@provider.function
def sync_auth() -> Auth:
    return Auth(username="sync-user", password="sync-pass")


@provider.asyncfunction
async def async_auth() -> Auth:
    await asyncio.sleep(0)  # Do some async work here...
    return Auth(username="async-user", password="async-pass")


@injector.function
def sync_get_auth(*, auth: Auth = required) -> str:
    return f"{auth.username}:{auth.password}"


@injector.asyncfunction
async def get_async_auth(*, auth: Auth = required) -> str:
    return f"{auth.username}:{auth.password}"


with sync_auth.scope(), async_auth.scope():
    assert sync_get_auth() == "sync-user:sync-pass"
    assert asyncio.run(get_async_auth()) == "async-user:async-pass"

with sync_auth.scope():
    assert asyncio.run(get_async_auth()) == "sync-user:sync-pass"
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

Username = NewType("Username", str)


@provider.function
def username() -> Username:
    return "alice"


@injector.function
def greeting(*, username: Username = required) -> str:
    return f"Hello, {username}!"


with username.scope():
    assert greeting() == "Hello, alice!"
```

### User-Defined Types

This includes types you or a third-party package define. In this case, an `Auth` class:

```python
from dataclasses import dataclass

from pybooster import injector
from pybooster import provider
from pybooster import required


@dataclass
class Auth:
    role: str
    username: str
    password: str


@provider.function
def auth() -> Auth:
    return Auth(role="user", username="alice", password="EGwVEo3y9E")


@injector.function
def login_message(*, auth: Auth = required) -> str:
    return f"Logged in as {auth.username}"


with auth.scope():
    assert login_message() == "Logged in as alice"
```

### Subclassed Types

Providers of subclasses will be automatically injected into functions that require the
base class. So an `AdminAuth` class that inherits from `Auth` can be injected into
functions that require `Auth`.

```python
from dataclasses import dataclass
from typing import Literal

from pybooster import injector
from pybooster import provider
from pybooster import required


@dataclass
class Auth:
    role: str
    username: str
    password: str


@dataclass
class AdminAuth(Auth):
    role: Literal["admin"]


@provider.function
def admin_auth() -> AdminAuth:
    return AdminAuth(role="admin", username="admin", password="admin")


@injector.function
def login_message(*, auth: Auth = required) -> str:
    return f"Logged in as {auth.username}"


with admin_auth.scope():
    assert login_message() == "Logged in as admin"
```

### Union Types

You can require a union of types by using the `Union` type or the `|` operator (where
supported). Doing so will resolve the first dependency that has a provider available in
the order declared by the union (left-to-right). This could be useful in case, as below,
where you have an `Employee` or `Contractor` class that are not related by inheritance.

```python
from dataclasses import dataclass

from pybooster import injector
from pybooster import provider
from pybooster import required


@dataclass
class Employee:
    name: str
    employee_id: int


@dataclass
class Contractor:
    name: str
    contractor_id: int


@provider.function
def employee() -> Employee:
    return Employee(name="Alice", employee_id=1)


@provider.function
def contractor() -> Contractor:
    return Contractor(name="Bob", contractor_id=2)


@injector.function
def greet(*, person: Employee | Contractor = required) -> str:
    return f"Hello, {person.name}!"


with employee.scope():
    assert greet() == "Hello, Alice!"

with contractor.scope():
    assert greet() == "Hello, Bob!"

with employee.scope(), contractor.scope():
    assert greet() == "Hello, Alice!"
```

### Tuple Types

You can provide a tuple of types from a provider in order to provide multiple
dependencies at once. This is useful in async or threaded providers when it would be
more efficient to gather dependencies in parallel. Or, as in the case below, if you need
to destructure some data into separate dependencies.

```python
import json
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import NewType

from pybooster import injector
from pybooster import provider
from pybooster import required

Username = NewType("Username", str)
Password = NewType("Password", str)

tempfile = NamedTemporaryFile()
SECRETS_JSON = Path(tempfile.name)
SECRETS_JSON.write_text('{"username": "alice", "password": "EGwVEo3y9E"}')


@provider.function
def username_and_password() -> tuple[Username, Password]:
    with SECRETS_JSON.open() as f:
        secrets = json.load(f)
    return Username(secrets["username"]), Password(secrets["password"])


@injector.function
def login_message(*, username: Username = required) -> str:
    return f"Logged in as {username}"


with username_and_password.scope():
    assert login_message() == "Logged in as alice"
```
