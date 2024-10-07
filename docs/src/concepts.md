# Concepts

## Providers

A provider is a synchronous or asynchronous function that creates or yields a
[dependency](#dependencies). Providers are used to define how dependencies are created
and managed by Ninject

### Defining Sync Providers

```python
from ninject import provider


class Config:
    username: str
    password: str


@provider.function
def config() -> Config:
    return Config(username='alice', password='EGwVEo3y9E')
```

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

```python
from asyncio import sleep
from ninject import provider


@provider.asyncfunction
async def async_config() -> Config:
    await sleep(1)  # Do some async work here...
    return Config(username='alice', password='EGwVEo3y9E')
```

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
```

### Parameterizing Providers

Providers can take parameters to customize the dependency they provide. These parameters

### Scoping Providers

Providers can be be made available within a scope using the `scope` method. This method
takes

## Injections

...

## Dependencies

A dependency is any Python type or class in Python. This includes types that are
built-in to Python, types from the standard library, types from third-party packages,
and types you'd use for annotations in your own code.

### Built-In Types

Ninject does not allow you to use built-in types directly. Instead you must use
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

Providers of subclasses will be automatically injected into functions that require the
base class. So an `AdminAuth` class that extends `Auth` will be injected into functions
that require `Auth`.

```python
from typing import Literal


@dataclass
class AdminAuth(Auth):
    role: Literal['admin']


@provider.function
def admin_auth() -> AdminAuth:
    return AdminAuth(role='admin', username='admin', password='admin')


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
