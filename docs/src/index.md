# Home

PyBooster is a dependency injection framework for Python that reduces boilerplate with
modern typing features.

## Install

```bash
pip install -U pybooster
```

## Quick Start

Getting started with PyBooster involves a few steps:

1. Define a [provider](concepts.md#providers) function for a
   [dependency](concepts.md#dependencies).
2. Add an [injector](concepts.md#injectors) to a function that will use that dependency.
3. Activate the [provider's scope](concepts.md#scoping-providers) and call injected
   function inside it.

Here's brief example showing how to inject a `sqlite3.Connection` object into a function
that executes a query:

```python
import sqlite3
from typing import Iterator

from pybooster import injector
from pybooster import provider
from pybooster import required


@provider.iterator
def sqlite_connection(database: str) -> Iterator[sqlite3.Connection]:
    with sqlite3.connect(database) as conn:
        yield conn


@injector.function
def query_database(query: str, *, conn: sqlite3.Connection = required) -> None:
    conn.execute(query)


with sqlite_connection.scope(":memory:"):
    query_database("CREATE TABLE example (id INTEGER PRIMARY KEY)")
```
