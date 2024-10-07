# Examples

This page contains examples of how to use Ninject to provide and inject dependencies.

## SQLite

This example demonstrates how to use Ninject to provide and inject a
`sqlite3.Connection` object:

```python
from sqlite3 import Connection
```

First, define a [provider](/concepts#providers) function for the dependency. In this
case, since the connection object is a context manager, we can use the
`@provider.iterator` decorator to create a generator that yields the connection object.
This allows Ninject to automatically close the connection when the scope is exited:

```python
from sqlite3 import connect
from typing import Iterator

from ninject import provider


@provider.iterator
def sqlite_connection(database: str) -> Iterator[Connection]:
    with connect(database) as conn:
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

Finally, activate the provider's scope and call the function:

```python
with sqlite_connection.scope('example.db'):
    query_database('CREATE TABLE example (id INTEGER PRIMARY KEY)')
```
