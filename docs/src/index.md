# Home

Ninject is a [dependency injection](https://en.wikipedia.org/wiki/Dependency_injection)
framework for Python that reduces boilerplate by leveraging modern typing features.

## Installation

```bash
pip install ninject
```

## Quick Start

Getting started with Ninject involves a few steps:

1. Define a [provider](concepts.md#providers) function for a
   [dependency](concepts.md#dependencies).
2. Add an [injector](concepts.md#injectors) to a function that will use that dependency.
3. Activate the [provider's scope](concepts.md#scoping-providers) and call injected
   function inside it.

Here's brief example showing how to inject a `sqlite3.Connection` object into a function
that executes a query:

```python
from sqlite3 import Connection

from ninject import provider, injector, required


@provider.iterator
def sqlite_connection(database: str) -> Iterator[Connection]:
    with connect(database) as conn:
        yield conn


@injector.function
def query_database(query: str, *, conn: Connection = required) -> None:
    with conn.cursor() as cursor:
        cursor.execute(query)


with sqlite_connection.scope('example.db'):
    query_database('CREATE TABLE example (id INTEGER PRIMARY KEY)')
```
