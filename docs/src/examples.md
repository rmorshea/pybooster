# Examples

## [Boto3](https://boto3.amazonaws.com/v1/documentation/api/latest/index.html)

```python
import json
from dataclasses import asdict
from dataclasses import dataclass
from typing import TYPE_CHECKING
from typing import Annotated
from typing import LiteralString
from typing import NewType

from boto3.session import Session
from botocore.client import BaseClient
from moto import mock_aws

from pybooster import injector
from pybooster import provider
from pybooster import required
from pybooster import solved

# Avoid importing mypy_boto3_s3 but still make S3Client available at runtime.
if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client
else:
    S3Client = Annotated[BaseClient, "S3Client"]


BucketName = NewType("BucketName", str)


@dataclass
class User:
    id: int
    name: str


@provider.function
def client_provider(service_name: LiteralString, *, session: Session = required) -> BaseClient:
    return session.client(service_name)


@provider.function
def bucket_provider(bucket_name: str, *, client: S3Client = required) -> BucketName:
    try:
        # Check if the bucket already exists
        client.head_bucket(Bucket=bucket_name)
    except client.exceptions.ClientError as e:
        # Create if it doesn't
        if e.response["Error"]["Code"] == "404":
            client.create_bucket(Bucket=bucket_name)
        else:
            raise
    return BucketName(bucket_name)


@injector.function
def put_user(
    user: User,
    *,
    bucket_name: BucketName = required,
    client: S3Client = required,
) -> None:
    data = json.dumps(asdict(user)).encode()
    client.put_object(Bucket=bucket_name, Key=f"user/{user.id}", Body=data)


@injector.function
def get_user(
    user_id: int,
    *,
    bucket_name: BucketName = required,
    client: S3Client = required,
) -> User:
    response = client.get_object(Bucket=bucket_name, Key=f"user/{user_id}")
    return User(**json.loads(response["Body"].read()))


def main():
    with mock_aws():  # Mock AWS services for testing purposes
        with (
            injector.shared((Session, Session())),
            solved(client_provider[S3Client].bind("s3"), bucket_provider.bind("my-bucket")),
            injector.shared(BucketName),
        ):
            user = User(id=1, name="Alice")
            put_user(user)
            assert get_user(user.id) == user


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
from pybooster import solved
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
    with solved(async_engine_provider.bind(DB_URL), async_session_provider):
        async with injector.shared(AsyncEngine) as values:
            async with values[AsyncEngine].begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            yield


@injector.asyncfunction
async def post_user(request: Request, *, session: AsyncSession = required) -> JSONResponse:
    async with session.begin():
        user = User(**(await request.json()))
        session.add(user)
        await session.flush()
        return JSONResponse({"id": user.id})


@injector.asyncfunction
async def get_user(request: Request, *, session: AsyncSession = required) -> JSONResponse:
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
from pybooster import solved
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
        solved(
            engine_provider.bind(url),
            session_provider.bind(expire_on_commit=False),
        ),
        injector.shared(Engine),
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
from pybooster import solved
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
    with solved(
        async_engine_provider.bind(url),
        async_session_provider.bind(expire_on_commit=False),
    ):
        async with injector.shared(AsyncEngine):
            await create_tables()
            user_id = await add_user("Alice")
            user = await get_user(user_id)
            assert user.name == "Alice"


asyncio.run(main())
```

## [SQLite](https://docs.python.org/3/library/sqlite3.html)

Shows how to create and read back a user from an SQLite database.

```python
import sqlite3
from collections.abc import Iterator
from typing import Self

from pybooster import injector
from pybooster import provider
from pybooster import required
from pybooster import solved


@provider.iterator
def sqlite_connection(database: str) -> Iterator[sqlite3.Connection]:
    with sqlite3.connect(database) as conn:
        yield conn


@injector.function
def make_user_table(*, conn: sqlite3.Connection = required) -> None:
    conn.execute("CREATE TABLE user (id INTEGER PRIMARY KEY, name TEXT)")
    conn.commit()


class User:
    def __init__(self, user_id: int, name: str):
        self.id = user_id
        self.name = name

    @injector.function
    def save(self, *, conn: sqlite3.Connection = required) -> None:
        conn.execute("INSERT INTO user (id, name) VALUES (?, ?)", (self.id, self.name))

    @classmethod
    @injector.function
    def load(cls, user_id: int, *, conn: sqlite3.Connection = required) -> Self:
        cursor = conn.execute("SELECT name FROM user WHERE id = ?", (user_id,))
        name = cursor.fetchone()[0]
        return cls(user_id, name)


def main():
    with (
        solved(sqlite_connection.bind(":memory:")),
        # Reusing the same connection is only needed for in-memory databases.
        injector.shared(sqlite3.Connection),
    ):
        make_user_table()
        user = User(1, "Alice")
        user.save()
        assert User.load(1).name == "Alice"


main()
```
