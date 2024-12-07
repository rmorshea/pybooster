# PyBooster 💉

[![PyPI - Version](https://img.shields.io/pypi/v/pybooster.svg)](https://pypi.org/project/pybooster)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> [!WARNING]
> This project is still under development - use at your own risk.

PyBooster - dependency injection without the boilerplate.

## Documentation

Learn more here: https://ryanmorshead.com/pybooster

## Install

```bash
pip install -U pybooster
```

## At a Glance

Getting started with PyBooster involves a few steps:

1. Define a [provider](https://ryanmorshead.com/pybooster/concepts#providers) function
    for a [dependency](https://ryanmorshead.com/pybooster/conceptsd#dependencies).
1. Add an [injector](https://ryanmorshead.com/pybooster/conceptsd#injectors) to a
    function that will use that dependency.
1. Activate a [solution](https://ryanmorshead.com/pybooster/conceptsd#solutions) and
    call the dependent function in its context.

The example below injects a `sqlite3.Connection` into a function that executes SQL:

```python
import sqlite3
from collections.abc import Iterator
from tempfile import NamedTemporaryFile

from pybooster import injector
from pybooster import provider
from pybooster import required
from pybooster import solved


@provider.iterator
def sqlite_connection(database: str) -> Iterator[sqlite3.Connection]:
    with sqlite3.connect(database) as conn:
        yield conn


@injector.function
def sql(cmd: str, *, conn: sqlite3.Connection = required) -> sqlite3.Cursor:
    return conn.execute(cmd)


tempfile = NamedTemporaryFile()
with solved(sqlite_connection.bind(tempfile.name)):
    sql("CREATE TABLE example (id INTEGER PRIMARY KEY, name TEXT)")
    sql("INSERT INTO example (name) VALUES ('alice')")
    cursor = sql("SELECT * FROM example")
    assert cursor.fetchone() == (1, "alice")
```

This works by inspecting the type hints of the provider `sqlite_connection` to see that
it produces a `sqlite3.Connection`. Simarly, the signature of the dependant function
`query_database` is inspected to see that it requires a `sqlite3.Connection`. At that
point, when `query_database` is called it checks to see if there's a
`sqlite3.Connection` provider in the current solution and, if so, injects it into the
function.
