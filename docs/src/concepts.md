# Concepts

This section cover's Ninjects core features and how to use them.

## Injectors

An injection takes place whenenever Ninject executes a [provider](#providers) while
resolving a [dependency](#dependencies). I

### Decorator Injectors

Ninject supplies a set of decorators that can be added to functions in order to inject
[dependencies](#dependencies). Dependencies for a decorated function are declared as
keyword-only arguments with a type annotation and a default value of `required`.

```python
from typing import NewType

from ninject import injector, required


Recipient = NewType('Recipient', str)


@injector.function
def hello_greeting(*, recipient: Recipient = required) -> str:
    return f'Hello, {recipient}!'
```

!!! note

    Don't forget to add the `required` default value. Without it, Ninject will not
    know that the argument is a dependency that needs to be injected.

In order for a value to be injected you'll need to declare a [provider](#providers) and
activate it:

```python
from ninject import provider


@provider.function
def alice() -> Recipient:
    return Recipient('Alice')


with alice.scope():
    assert hello_greeting() == 'Hello, Alice!'
```

Ninject supports decorators for the following types of functions:

-   `injector.function`
-   `injector.asyncfunction`
-   `injector.generator`
-   `injector.asyncgenerator`
-   `injector.contextmanager`
-   `injector.asynccontextmanager`

You can use all of these decorators on methods of a class as well.

### Inline Injector

If you need to access the current value of a dependency outside of a function, you can
use `injector.current` by activating it either as a synchronous or asynchronous context
manager.

```python
from typing import NewType

from ninject import injector, provider, required

Recipient = NewType('Recipient', str)


@provider.function
def alice() -> Recipient:
    return Recipient('Alice')


with alice.scope():
    with injector.current(Recipient) as recipient:
        assert recipient == 'Alice'
```

## Providers

A provider is a function that creates or yields a [dependency](#dependencies). Providers
are used to define how dependencies resolved when they are [injected](#injectors) into a
function or context. What providers are available depends on what scopes are active when
a dependency is resolved.

### Defining Sync Providers

Sync providers can either be functions the return a dependency's value:

```python
from ninject import provider


class Config:
    username: str
    password: str


@provider.function
def config() -> Config:
    return Config(username='alice', password='EGwVEo3y9E')
```

Or iterators that yield the dependency's value. Iterators are useful when you have
resources that need to be cleaned up when the dependency's value is no longer in use.

```python
from typing import Iterator
from sqlite3 import Connection

from ninject import provider


@provider.iterator
def sqlite_connection() -> Iterator[Connection]:
    with connect('example.db') as conn:
        yield conn
```

### Defining Async Providers

Async providers can either be a coroutine function that returns a dependency's value:

```python
from asyncio import sleep
from ninject import provider


@provider.asyncfunction
async def async_config() -> Config:
    await sleep(1)  # Do some async work here...
    return Config(username='alice', password='EGwVEo3y9E')
```

Or async iterators that yield the dependency's value. Async iterators are useful when
you have resources that need to be cleaned up when the dependency's value is no longer
in use.

```python
from asyncio import open_connection, StreamReader
from typing import AsyncIterator

from ninject import provider


@provider.asynciterator
async def example_reader() -> AsyncIterator[StreamReader]:
    reader, writer = await open_connection('example.com', 80)
    writer.write(b'GET / HTTP/1.1\r\nHost: example.com\r\n\r\n')
    await writer.drain()
    try:
        yield reader
    finally:
        writer.close()
        await writer.wait_closed()
```

### Mixing Sync/Async Providers

You can define both sync and async providers for the same dependency. Sync providers can
be used in async contexts, but not the other way around. Ninject will always choose to
use an async provider when running in an async context and one is available.

```python
import asyncio

from ninject import injector, provider, required


class Config:
    username: str
    password: str


@provider.function
def config() -> Config:
    return Config(username='sync-user', password='sync-pass')


@provider.asyncfunction
async def async_config() -> Config:
    await sleep(1)  # Do some async work here...
    return Config(username='async-user', password='async-pass')


@injector.function
def get_config(*, config: Config = required) -> str:
    return f'{config.username}:{config.password}'


@injector.asyncfunction
async def get_async_config(*, config: Config = required) -> str:
    return f'{config.username}:{config.password}'


with config.scope(), async_config.scope():
    assert get_config() == 'sync-user:sync-pass'
    assert asyncio.run(get_async_config()) == 'async-user:async-pass

with config.scope():
    assert asyncio.run(get_async_config()) == 'sync-user:sync-pass'
```

### Parameterizing Providers

You can add parameters to a provider by adding them to the provider function signature.

```python
import sqlite3

from ninject import provider


@provider.iterator
def sqlite_connection(database: str) -> Iterator[sqlite3.Connection]:
    with sqlite3.connect(database) as conn:
        yield conn
```

These parameters can be passed to the provider when activating the scope.

```python
with sqlite_connection.scope('example.db'):
    ...
```

You can also declare these parameters as dependencies by making them keyword-only,
annotating them with the desired type, and setting the default value to `required`.

```python
import os
import sqlite3

from ninject import provider


Database = NewType('DatabasePath', str)


@provider.function
def sqlite_database() -> Database:
    return Database(os.environ.get('SQLITE_DATABASE', 'example.db'))


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

from ninject import provider

Recipient = NewType('Recipient', str)


@provider.function
def alice() -> Recipient:
    return Recipient('Alice')


with alice.scope():
    ...  # alice is available to inject
```

You can override a dependency's provider by activating a new scope for the same
dependency.

```python
from typing import NewType

from ninject import provider, injector


Recipient = NewType('Recipient', str)


@provider.function
def alice() -> Recipient:
    return Recipient('Alice')


@provider.function
def bob() -> Recipient:
    return Recipient('Bob')


@injector.function
def get_recipient(*, recipient: Recipient = required) -> str:
    return recipient


with alice.scope():
    assert get_recipient() == 'Alice'
    with bob.scope():
        assert get_recipient() == 'Bob'
    assert get_recipient() == 'Alice'
```

!!! note

    The exact behavior of scopes can depend on whether the requested dependency is
    a [union](#union-types) or has [subclasses](#subclassed-types).

## Dependencies

A dependency is (almost) any Python type or class.

### Built-In Types

Ninject does not allow you to use built-in types directly. Instead you should use
[`NewType`](https://docs.python.org/3/library/typing.html#newtype) to define a distinct
subtype so that it is easily identifiable. For example, instead of using `str` to
represent a username, you might define a `Username` new type like this:

```python
from typing import NewType

Username = NewType('Username', str)
```

Now you can make a [provider](#providers) for `Username` and inject it into functions.

```python
from ninject import injector, provider, required


@provider.function
def username() -> Username:
    return 'alice'


@injector.function
def greeting(*, username: Username = required) -> str:
    return f'Hello, {username}!'


with username.scope():
    assert greeting() == 'Hello, alice!'
```

### User-Defined Types

This includes types you or a third-party package define. In this case, an `Auth` class:

```python
from dataclasses import dataclass

from ninject import provider


@dataclass
class Auth:
    role: str
    username: str
    password: str


@provider.function
def auth() -> Auth:
    return Auth(role='user', username='alice', password='EGwVEo3y9E')


@injector.function
def login_message(*, auth: Auth = required) -> str:
    return f'Logged in as {auth.username}'


with auth.scope():
    assert login_message() == 'Logged in as alice'
```

### Subclassed Types

Providers of subclasses will be automatically injected into functions that require the
base class. So an `AdminAuth` class that extends `Auth` will be injected into functions
that require `Auth`.

```python
from dataclasses import dataclass
from typing import Literal

from ninject import injector, provider, required


@dataclass
class Auth:
    role: str
    username: str
    password: str


@dataclass
class AdminAuth(Auth):
    role: Literal['admin']


@provider.function
def admin_auth() -> AdminAuth:
    return AdminAuth(role='admin', username='admin', password='admin')


@injector.function
def login_message(*, auth: Auth = required) -> str:
    return f'Logged in as {auth.username}'


with admin_auth.scope():
    assert login_message() == 'Logged in as admin'
```

### Union Types

You can require a union of types by using the `Union` type or the `|` operator (where
supported). Doing so will resolve, in order, the inner-most provider scope that matches
one of the types in the union. This could be useful in case, as below, where you have an
`Employee` or `Contractor` class that are not related by inheritance.

```python
from ninject import provider, injector, required


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
    return Employee(name='Alice', employee_id=1)


@provider.function
def contractor() -> Contractor:
    return Contractor(name='Bob', contractor_id=2)


@injector.function
def greet(*, person: Union[Employee, Contractor] = required) -> str:
    return f'Hello, {person.name}!'


with employee.scope():
    assert greet() == 'Hello, Alice!'

with contractor.scope():
    assert greet() == 'Hello, Bob!'

with employee.scope(), contractor.scope():
    assert greet() == 'Hello, Bob!'
```

### Tuple Types

You can provide a tuple of types from a provider in order to provide multiple
dependencies at once. This is useful in async or threaded providers when it would be
more efficient to gather dependencies in parallel. Or, as in the case below, if you need
to destructure some data into separate dependencies.

```python
import json
from typing import NewType

from ninject import provider, injector, required

Username = NewType('Username', str)
Password = NewType('Password', str)


@provider.function
def username_and_password() -> tuple[Username, Password]:
    with open('secrets.json') as f:
        secrets = json.load(f)
    return Username(secrets['username']), Password(secrets['password'])


@injector.function
def login_message(*, username: Username = required) -> str:
    return f'Logged in as {username}'


with username_and_password.scope():
    assert login_message() == 'Logged in as alice'
```

## Singletons

By default, Ninject will create a new instance of a dependency each time it is injected.
To change this, using the `singleton` context manager to declare that a dependency
should be shared across all injections for the duration of a context. This will
immediately execute the provider and store the result for future injections.

```python
from dataclasses import dataclass
from ninject import provider, injector, required, singleton


@dataclass
class Auth:
    username: str
    password: str


@provider.function
def auth() -> Auth:
    return Auth(username='alice', password='EGwVEo3y9E')


@injector.function
def get_auth(*, auth: Auth = required) -> Auth:
    return auth


with auth.scope():

    assert get_auth() is not get_auth()

    with singleton(Auth):
        assert get_auth() is get_auth()
```

If the dependency's provider might be asynchronous, enter the `singleton()` context
manager using `async with` instead. If you in an async context you should default to
using `async with` to ensure that async providers can be executed successfully.
