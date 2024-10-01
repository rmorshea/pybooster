# Home

A modern [dependency injection](https://en.wikipedia.org/wiki/Dependency_injection)
framework for Python.

## Installation

```bash
pip install ninject
```

## Basic Usage

Start by selecting or defining a class that you want to use as a dependency. The
dependency can be a standard class or even a type annotation. This example will use a
`sqlite3.Connection`:

```python
from sqlite3 import Connection
```

Next define a [provider](/providers) function for that dependency and add a `provider`
decorator to it. Since the `sqlite3.Connection` object should be opened and closed for
each use, the provider should return an iterator that yields the connection object. As
such you'll use the `@provider.iterator` decorator.

```python
from sqlite3 import connect
from typing import Iterator

from ninject import provider


@provider.iterator
def sqlite_connection(path: str) -> Iterator[Connection]:
    with connect(path) as conn:
        yield conn
```

!!! note

    Take care to annotate the return type of the provider function appropriately since
    this is how Ninject will determine the type of the dependency it provides. If for
    some reason you cannot annotate the return type or Ninject incorrectly infers the
    type you can pass the dependency type as via the `provides` argument to the decorator.

    ```python
    @provider.iterator(provides=Connection)
    ```

Now define a function that you want to inject the dependency into. To do this, first add
the appropriate `injector` decorator to the function and second, add a keyword-only
parameter that is marked for injection using `required` as its default value:

```python
from ninject import injector, required


@injector.function
def query_database(query: str, *, conn: Connection = required) -> None:
    with conn.cursor() as cursor:
        cursor.execute(query)
```

Finally, activate the provider and call the function:

```python
with sqlite_connection.provide('example.db'):
    query_database('CREATE TABLE example (id INTEGER PRIMARY KEY)')
```
