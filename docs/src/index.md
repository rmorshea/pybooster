# PyBooster

Dependency injection without the boilerplate.

## Install

```bash
pip install -U pybooster
```

## At a Glance

Getting started with PyBooster involves a few steps:

1. Define a [provider](concepts.md#providers) function for a
   [dependency](concepts.md#dependencies).
2. Add an [injector](concepts.md#injectors) to a function that will use that dependency.
3. Active a [solution](concepts.md#solutions) and call the dependent function in it.

The example below injects a `sqlite3.Connection` into a function that executes a query:

```python
import sqlite3
from typing import Iterator

from pybooster import injector
from pybooster import provider
from pybooster import required
from pybooster import solution


@provider.iterator
def sqlite_connection(database: str) -> Iterator[sqlite3.Connection]:
    with sqlite3.connect(database) as conn:
        yield conn


@injector.function
def query_database(query: str, *, conn: sqlite3.Connection = required) -> None:
    conn.execute(query)


with solution(sqlite_connection.bind(":memory:")):
    query_database("CREATE TABLE example (id INTEGER PRIMARY KEY)")
```

This works by inspecting the type hints of the provider `sqlite_connection` to see that
it produces a `sqlite3.Connection`. Simarly, the signature of the dependant function
`query_database` is inspected to see that it requires a `sqlite3.Connection`. At that
point, when `query_database` is called it checks to see if there's a
`sqlite3.Connection` provider in the current soltion and, if so, injects it into the
function.