# Integrations

PyBooster supplies implementations for a number of popular tools and libraries.

## ASGI Apps

PyBooster's use of [`contextvars`](https://docs.python.org/3/library/contextvars.html)
under the hood can cause problems when state should live for the lifespan of an ASGI
application. However this can be solved with a middleware provided by PyBooster. All
you'll need to do is either wrap your ASGI application in it or pass it to your chosen
framework's middleware system.

```python
from pybooster.extra.asgi import PyBoosterMiddleware

your_app = ...
app = PyBoosterMiddleware(your_app)
```

See the [Starlette + SQLAlchemy example](examples.md#starlette-sqlalchemy) for one way
to use this middleware.

## SQLAlchemy

PyBooster's SQLAlchemy integration supplies providers for the following dependencies:

| Provider                                               | Dependency                                            |
| ------------------------------------------------------ | ----------------------------------------------------- |
| [`pybooster.extra.sqlalchemy.provide_engine`][]        | [`Engine`][sqlalchemy.engine.Engine]                  |
| [`pybooster.extra.sqlalchemy.provide_session`][]       | [`Session`][sqlalchemy.orm.Session]                   |
| [`pybooster.extra.sqlalchemy.provide_async_engine`][]  | [`AsyncEngine`][sqlalchemy.ext.asyncio.AsyncEngine]   |
| [`pybooster.extra.sqlalchemy.provide_async_session`][] | [`AsyncSession`][sqlalchemy.ext.asyncio.AsyncSession] |

The sync and async session providers are [generic](./concepts.md#generic-providers) on
their first positional argument which allows session subclasses to be used as
dependencies instead. For example:

```python
from sqlalchemy.orm import Session

from pybooster.extra.sqlalchemy import provide_session


class MySession(Session): ...


provide_my_session = provide_session.bind(MySession)
```

See the [Starlette + SQLAlchemy example](examples.md#starlette-sqlalchemy) for one way
to use these providers.
