from __future__ import annotations

from collections.abc import AsyncIterator
from collections.abc import Callable
from collections.abc import Iterator
from typing import TYPE_CHECKING
from typing import Any
from typing import ParamSpec
from typing import Protocol

from sqlalchemy import Engine
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import Session
from typing_extensions import TypeVar

from pybooster import provider
from pybooster.extra._utils import copy_signature

P = ParamSpec("P")
F = TypeVar("F", bound=Callable)

S = TypeVar("S", bound=Session, default=Session)
S_co = TypeVar("S_co", bound=Session, covariant=True)
A = TypeVar("A", bound=AsyncSession, default=AsyncSession)
A_co = TypeVar("A_co", bound=AsyncSession, covariant=True)


class SessionMaker(Protocol[P, S_co]):
    """A protocol for creating a SQLAlchemy session."""

    def __call__(self, bind: Engine = ..., *args: P.args, **kwargs: P.kwargs) -> S_co:
        """Create a SQLAlchemy session."""
        ...


class AsyncSessionMaker(Protocol[P, A_co]):
    """A protocol for creating an async SQLAlchemy session."""

    def __call__(self, bind: AsyncEngine = ..., *args: P.args, **kwargs: P.kwargs) -> A_co:
        """Create an async SQLAlchemy session."""
        ...


if TYPE_CHECKING:

    def _session_provider(
        cls: SessionMaker[P, S] = Session,
        bind: Engine = ...,
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> Iterator[S]: ...

    def _async_session_provider(
        cls: AsyncSessionMaker[P, A] = AsyncSession,
        bind: AsyncEngine = ...,
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> AsyncIterator[A]: ...

else:

    def _session_provider(cls=Session, **kwargs):
        with cls(**kwargs) as session:
            yield session

    async def _async_session_provider(cls=AsyncSession, **kwargs):
        async with cls(**kwargs) as session:
            yield session


@provider.iterator
@copy_signature(create_engine)
def engine_provider(*args: Any, **kwargs: Any) -> Iterator[Engine]:
    """Provide a SQLAlchemy engine."""
    engine = create_engine(*args, **kwargs)
    try:
        yield engine
    finally:
        engine.dispose()


@provider.asynciterator
@copy_signature(create_async_engine)
async def async_engine_provider(*args: Any, **kwargs: Any) -> AsyncIterator[AsyncEngine]:
    """Provide an async SQLAlchemy engine."""
    engine = create_async_engine(*args, **kwargs)
    try:
        yield engine
    finally:
        await engine.dispose()


def _infer_session_type(cls: type[S] = Session, *_args, **_kwargs) -> type[S]:
    return cls


def _infer_async_session_type(cls: type[A] = AsyncSession, *_args, **_kwargs) -> type[A]:
    return cls


session_provider = provider.iterator(
    _session_provider,
    requires={"bind": Engine},
    provides=_infer_session_type,
)
"""Provide a SQLAlchemy session."""


async_session_provider = provider.asynciterator(
    _async_session_provider,
    requires={"bind": AsyncEngine},
    provides=_infer_async_session_type,
)
"""Provide an async SQLAlchemy session."""
