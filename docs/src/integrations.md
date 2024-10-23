# Integrations

PyBooster supplies implementations for a number of popular tools and libraries.

## ASGI Frameworks

PyBooster supplies a light-weight ASGI middleware that allows you to declare
[providers](concepts.md#providers) or [shared contexts/values](concepts.md#sharing) that
should be made available over the lifetime of the application instead of per-request.
All you'll need to do is either wrap your ASGI application in it or pass it to your
chosen framework's middleware system.

```python
from pybooster.extra.asgi import PyBoosterMiddleware

your_app = ...
app = PyBoosterMiddleware(your_app)
```

See the [Starlette + SQLAlchemy example](examples.md#starlette-sqlalchemy) for one way
to use this middleware.

## SQLAlchemy
