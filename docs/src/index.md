# Basics

Ninject is a modern
[dependency injection](https://en.wikipedia.org/wiki/Dependency_injection) framework for
Python that reduces boilerplate and improves testability by providing a simple and
intuitive API for managing dependencies.

## Installation

```bash
pip install ninject
```

## Usage

Getting started with Ninject involves four main steps:

1. Pick a type you want to inject - this will be the dependency.
2. Define a provider function for that dependency.
3. Mark a function that you want to inject the dependency into.
4. Activate the provider's scope and call the function within that scope.

Here's an example that demonstrates how to use Ninject to provide and inject a
`sqlite3.Connection` object into a function that executes a query:

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

A more detailed step-by-step guide for this example can be found in the
[examples](/examples#sqlite).
