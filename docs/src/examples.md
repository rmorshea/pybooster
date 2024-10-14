# Examples

## [Boto3](https://boto3.amazonaws.com/v1/documentation/api/latest/index.html)

```python
from typing import TYPE_CHECKING
from typing import Annotated

from boto3.session import Session
from botocore.client import BaseClient
from moto import mock_aws

from pybooster import injector
from pybooster import provider
from pybooster import required
from pybooster import shared

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client
else:
    S3Client = Annotated[BaseClient, "mypy_boto3_s3.S3Client"]


@provider.function
def aws_client(service_name: str, *, session: Session = required) -> BaseClient:
    return session.client(service_name)


@injector.function
def create_bucket(bucket_name: str, *, client: S3Client = required) -> None:
    client.create_bucket(Bucket=bucket_name)


@injector.function
def list_buckets(*, client: S3Client = required) -> list[str]:
    return [bucket["Name"] for bucket in client.list_buckets()["Buckets"]]


def main():
    with mock_aws():  # Mock AWS services for testing purposes
        with shared(Session, value=Session()), aws_client[S3Client].scope("s3"):
            create_bucket("my-bucket")
            assert "my-bucket" in list_buckets()


main()
```

## [Starlette](https://www.starlette.io/) + [SQLAlchemy](https://www.sqlalchemy.org/)

```python
import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from pybooster import injector
from pybooster import required
from pybooster import shared
from pybooster.extra.asgi import PyBoosterMiddleware
from pybooster.extra.sqlalchemy import async_engine_provider
from pybooster.extra.sqlalchemy import async_session_provider


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "user"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column()


DB_URL = "sqlite+aiosqlite:///:memory:"


@asynccontextmanager
async def sqlalchemy_lifespan(_: Starlette) -> AsyncIterator[None]:
    with async_engine_provider.scope(DB_URL):  # set up the engine provider
        async with shared(AsyncEngine) as engine:  # establish the engine as a singleton

            # create tables if they don't exist
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

            with async_session_provider.scope():  # set up the transaction provider
                yield


@injector.asyncfunction
async def post_user(
    request: Request, *, session: AsyncSession = required
) -> JSONResponse:
    async with session.begin():
        user = User(**(await request.json()))
        session.add(user)
        await session.flush()
        return JSONResponse({"id": user.id})


@injector.asyncfunction
async def get_user(
    request: Request, *, session: AsyncSession = required
) -> JSONResponse:
    user = await session.get(User, request.path_params["id"])
    return JSONResponse(None if user is None else {"id": user.id, "name": user.name})


app = Starlette(
    routes=[
        Route("/user", post_user, methods=["POST"]),
        Route("/user/{id:int}", get_user, methods=["GET"]),
    ],
    lifespan=sqlalchemy_lifespan,
    middleware=[Middleware(PyBoosterMiddleware)],
)


async def main():
    with TestClient(app) as client:
        response = client.post("/user", json={"name": "Alice"})
        assert response.status_code == 200
        assert response.json() == {"id": 1}

        response = client.get("/user/1")
        assert response.status_code == 200
        assert response.json() == {"id": 1, "name": "Alice"}

        response = client.get("/user/2")
        assert response.status_code == 200
        assert response.json() is None


asyncio.run(main())
```

## [SQLAlchemy](https://www.sqlalchemy.org/)

```python
from sqlalchemy import Engine
from sqlalchemy import select
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import Session
from sqlalchemy.orm import mapped_column

from pybooster import injector
from pybooster import required
from pybooster import shared
from pybooster.extra.sqlalchemy import engine_provider
from pybooster.extra.sqlalchemy import session_provider


class Base(DeclarativeBase): ...


class User(Base):
    __tablename__ = "user"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]


@injector.function
def create_tables(*, session: Session = required) -> None:
    Base.metadata.create_all(session.bind)


@injector.function
def add_user(name: str, *, session: Session = required) -> int:
    with session.begin():
        user = User(name=name)
        session.add(user)
        session.flush()
        return user.id


@injector.function
def get_user(user_id: int, *, session: Session = required) -> User:
    return session.execute(select(User).where(User.id == user_id)).scalar_one()


def main():
    url = "sqlite:///:memory:"
    with (
        engine_provider.scope(url),
        shared(Engine),
        session_provider.scope(expire_on_commit=False),
    ):
        create_tables()
        user_id = add_user("Alice")
        user = get_user(user_id)
        assert user.name == "Alice"


main()
```

## [SQLAlchemy (Async)](https://www.sqlalchemy.org/)

```python
import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from pybooster import injector
from pybooster import required
from pybooster import shared
from pybooster.extra.sqlalchemy import async_engine_provider
from pybooster.extra.sqlalchemy import async_session_provider


class Base(DeclarativeBase): ...


class User(Base):
    __tablename__ = "user"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]


@injector.asyncfunction
async def create_tables(*, engine: AsyncEngine = required) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@injector.asyncfunction
async def add_user(name: str, *, session: AsyncSession = required) -> int:
    async with session.begin():
        user = User(name=name)
        session.add(user)
        await session.flush()
        return user.id


@injector.asyncfunction
async def get_user(user_id: int, *, session: AsyncSession = required) -> User:
    return (await session.execute(select(User).where(User.id == user_id))).scalar_one()


async def main():
    url = "sqlite+aiosqlite:///:memory:"
    with async_engine_provider.scope(url):
        async with shared(AsyncEngine):
            with async_session_provider.scope(expire_on_commit=False):
                await create_tables()
                user_id = await add_user("Alice")
                user = await get_user(user_id)
                assert user.name == "Alice"


asyncio.run(main())
```

## [SQLite](https://docs.python.org/3/library/sqlite3.html)

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


def main():
    with sqlite_connection.scope(":memory:"):
        query_database("CREATE TABLE example (id INTEGER PRIMARY KEY)")


main()
```
