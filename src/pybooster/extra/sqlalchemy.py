from __future__ import annotations

from collections.abc import AsyncIterator
from collections.abc import Callable
from collections.abc import Iterator
from typing import Any
from typing import ParamSpec

from sqlalchemy import Engine
from sqlalchemy import create_engine
from sqlalchemy.engine import URL  # noqa: TC002
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import Session
from typing_extensions import TypeVar

from pybooster import provider

P = ParamSpec("P")
F = TypeVar("F", bound=Callable)

S = TypeVar("S", bound=Session, default=Session)
A = TypeVar("A", bound=AsyncSession, default=AsyncSession)


@provider.contextmanager
def engine_provider(url: str | URL, **kwargs: Any) -> Iterator[Engine]:
    """Provide a SQLAlchemy engine."""
    engine = create_engine(url, **kwargs)
    try:
        yield engine
    finally:
        engine.dispose()


@provider.asynccontextmanager
async def async_engine_provider(url: str | URL, **kwargs: Any) -> AsyncIterator[AsyncEngine]:
    """Provide an async SQLAlchemy engine."""
    engine = create_async_engine(url, **kwargs)
    try:
        yield engine
    finally:
        await engine.dispose()


def _infer_session_type(cls: type[S] = Session, *_args, **_kwargs) -> type[S]:
    return cls


def _infer_async_session_type(cls: type[A] = AsyncSession, *_args, **_kwargs) -> type[A]:
    return cls


@provider.contextmanager(requires={"bind": Engine}, provides=_infer_session_type)
def session_provider(
    cls: Callable[..., S] = Session,
    *args: Any,
    **kwargs: Any,
) -> Iterator[S]:
    """Provide a SQLAlchemy [session][sqlalchemy.orm.Session].

    Args:
        cls: The session class to instantiate. Defaults to `Session`.
        args: Positional arguments to pass to the session constructor.
        kwargs: Keyword arguments to pass to the session constructor.
    """
    with cls(*args, **kwargs) as session:
        yield session


@provider.asynccontextmanager(requires={"bind": AsyncEngine}, provides=_infer_async_session_type)
async def async_session_provider(
    cls: Callable[..., A] = AsyncSession,
    *args: Any,
    **kwargs: Any,
) -> AsyncIterator[A]:
    """Provide an async SQLAlchemy [session][sqlalchemy.ext.asyncio.AsyncSession].

    Args:
        cls: The session class to instantiate. Defaults to `AsyncSession`.
        args: Positional arguments to pass to the session constructor.
        kwargs: Keyword arguments to pass to the session constructor.
    """
    async with cls(*args, **kwargs) as session:
        yield session
