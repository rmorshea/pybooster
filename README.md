# PyBooster 💉

[![PyPI - Version](https://img.shields.io/pypi/v/pybooster.svg)](https://pypi.org/project/pybooster)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/pybooster.svg)](https://pypi.org/project/pybooster)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

PyBooster - dependency injection without the boiler plate.

## Documentation

Learn more here: https://ryanmorshead.com/pybooster

## Install

```bash
pip install -U pybooster
```

## At a Glance

Getting started with PyBooster involves a few steps:

1. Define a [provider](https://ryanmorshead.com/pybooster/features#providers) function
    for a [dependency](https://ryanmorshead.com/pybooster/features#dependencies).
1. Add an [injector](https://ryanmorshead.com/pybooster/features#injectors) to a
    function that will use that dependency.
1. Enter the
    [provider's scope](https://ryanmorshead.com/pybooster/features#scoping-providers) and
    call the dependent function in it.

The example below injects a `sqlite3.Connection` into a function that executes a query:

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

This works by inspecting the type hints of the provider `sqlite_connection` to see that
it produces a `sqlite3.Connection`. Simarly, the signature of the dependant function
`query_database` is inspected to see that it requires a `sqlite3.Connection`. At that
point, when `query_database` is called it checks to see if there's a
`sqlite3.Connection` provider in scope and, if so, injects it into the function.
