# Examples

This page contains examples of how to use Ninject to provide and inject dependencies.

## [SQLite](https://docs.python.org/3/library/sqlite3.html)

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

## [SQLAlchemy](https://www.sqlalchemy.org/)

```python
from collections.abc import Iterator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session

from ninject import injector, provider, required, singleton


class User(DeclarativeBase):
    __tablename__ = "users"
    id: Mapped[int]
    name: Mapped[str]


@provider.iterator
def sqlalchemy_engine(url: str) -> Iterator[Engine]:
    engine = create_engine(url)
    try:
        yield engine
    finally:
        engine.dispose()


@provider.iterator
def sqlalchemy_session(engine: Engine) -> Iterator[Session]:
    with Session(bind=engine).begin() as session:
        yield session


@injector.function
def test(*, session: Session = required):
    user = User(name="John")
    session.add(user)
    session.commit()
    assert session.query(User).filter(User.name == "John").one().name == "John"


url = "sqlite:///:memory:"
with (
    sqlalchemy_engine.scope(url),
    sqlalchemy_session.scope(),
    singleton(Engine),
):
    test()
```
