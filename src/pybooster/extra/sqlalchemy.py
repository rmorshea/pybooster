from __future__ import annotations

from collections.abc import AsyncIterator  # noqa: TCH003
from collections.abc import Iterator  # noqa: TCH003
from typing import Any
from typing import ParamSpec
from typing import TypeVar

from sqlalchemy import Engine
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import Session

from pybooster import provider
from pybooster import required
from pybooster.extra._utils import copy_signature

P = ParamSpec("P")
R = TypeVar("R")

__all__ = (
    "AsyncEngine",
    "AsyncSession",
    "async_engine_provider",
    "async_session_provider",
    "engine_provider",
    "session_provider",
)


@provider.iterator
@copy_signature(create_engine)
def engine_provider(*args: Any, **kwargs: Any) -> Iterator[Engine]:
    """Provide a SQLAlchemy engine."""
    engine = create_engine(*args, **kwargs)
    try:
        yield engine
    finally:
        engine.dispose()


@provider.iterator
@copy_signature(Session)  # not entirely accurate since `bind` can be possitional
def session_provider(*, bind: Engine = required, **kwargs: Any) -> Iterator[Session]:
    """Provide a SQLAlchemy session."""
    with Session(bind, **kwargs) as session:
        yield session


@provider.asynciterator
@copy_signature(create_async_engine)
async def async_engine_provider(*args: Any, **kwargs: Any) -> AsyncIterator[AsyncEngine]:
    """Provide a SQLAlchemy async engine."""
    engine = create_async_engine(*args, **kwargs)
    try:
        yield engine
    finally:
        await engine.dispose()


@provider.asynciterator
@copy_signature(AsyncSession)  # not entirely accurate since `bind` can be possitional
async def async_session_provider(*, bind: AsyncEngine = required, **kwargs: Any) -> AsyncIterator[AsyncSession]:
    """Provide a SQLAlchemy async session."""
    async with AsyncSession(bind, **kwargs) as session:
        yield session
