# Tutorial

This tutorial will walk you through creating an application which takes advantage of
PyBooster. Specifically, a media storage app similar to the one described in
[this video](https://www.youtube.com/watch?v=J1f5b4vcxCQ) by
[CodeAesthetic](https://www.youtube.com/@CodeAesthetic). The app will include an
`/upload` endpoint that accepts a file, processes it, and saves it using a blob storage
service. The business of uploading a file will be broken down into several steps where a
preview of the file is generated, the content is encrypted, and the file is saved to a
storage service. Each step will be represented by a separate interface, allowing for
easy testing and modular development. Visually, that should all look something like
this:

```mermaid
flowchart LR
    media@{ shape: pill, label: "Media"}
    preview@{ shape: pill, label: "Preview"}
    bytes@{ shape: pill, label: "Data"}
    preview_generator@{shape: rect, label: "Preview Generator"}
    encryptor@{ shape: rect, label: "Encryptor" }
    storage@{ shape: rect, label: "Storage" }

    media-->preview_generator
    preview_generator-->preview
    preview-->encryptor
    media-->encryptor
    encryptor-->bytes
    bytes-->storage
```

## Project Setup

To get started you can initialize a project using [UV](https://docs.astral.sh/uv/):

```bash
uv init
```

Among other things, this will spawn new `pyproject.toml` and `main.py` files. You'll
then want to add a few dependencies:

```bash
uv add litestar pybooster aiocache pillow
```

!!! note

    This tutorial will use [Litestar](https://docs.litestar.dev) for the web framework, but
    you can use any framework you like. The concepts will be the same.

## Basic Server

To the `main.py` file you'll begin by establishing a server with a single `/upload`
route handler that's responsible for processing file uploads. To this you'll specify the
necessary request and response contracts:

```python
from dataclasses import dataclass

from litestar import Litestar
from litestar import put


@dataclass
class UploadData:
    content_b64: str
    content_type: str
    storage_name: str


@put("/upload")
async def upload(data: UploadData) -> str: ...


app = Litestar(route_handlers=[upload])
```

!!! hint

    See [Litestar's documentation](https://docs.litestar.dev/) for more info on
    the details of defining route handlers.

## Route Logic

To start out you'll want to establishing interfaces that match up with the components in
the diagram above:

```python
from collections.abc import Collection
from typing import Protocol


class Encryptor(Protocol):
    def encrypt(self, plain: bytes) -> bytes: ...
    def decrypt(self, cipher: bytes) -> bytes: ...


class PreviewGenerator(Protocol):
    def generate(self, content: bytes) -> bytes: ...


class Storage(Protocol):
    async def save(self, prefix: str, data: dict[str, bytes]) -> None: ...
    async def load(self, prefix: str, keys: Collection[str]) -> dict[str, bytes]: ...
```

You can flesh out the `/upload` route's logic assuming these interfaces exist:

!!! note

    In the next section you'll see how to get instances of these interfaces into the
    route handler using PyBooster.

```python
from base64 import b64decode
from collections.abc import Mapping
from uuid import uuid4

PreviewGeneratorMap = Mapping[str, PreviewGenerator]
StorageMap = Mapping[str, Storage]


@put("/upload")
async def upload(data: UploadData) -> str:
    encryptor: Encryptor = ...
    preview_generators: PreviewGeneratorMap = ...
    storages: StorageMap = ...

    raw = b64decode(data.content_b64)
    preview = preview_generators[data.content_type].generate(raw)

    raw_encrypted = encryptor.encrypt(raw)
    preview_encrypted = encryptor.encrypt(preview)

    prefix = uuid4().hex
    img_data = {"raw": raw_encrypted, "preview": preview_encrypted}
    await storages[data.storage_name].save(prefix, img_data)

    return prefix


app = Litestar(route_handlers=[upload])
```

## Injecting Parameters

To inject the interfaces you'll now want to replace the `...` placeholder variables in
the `/upload` route handler with parameters that are resolved using PyBooster. This is
done by adding the [`asyncfunction`][pybooster.core.injector.asyncfunction] injector and
corresponding [`required`][pybooster.core.injector.required] parameters to the route
handler. In this case we need to set `hide_signature=True` which removes injected
parameters from the function signature in order to keep them from being treated as
request parameters.

```python
from pybooster import injector
from pybooster import required


@put("/upload")
@injector.asyncfunction(hide_signature=True)
async def upload(
    data: UploadData,
    *,
    encryptor: Encryptor = required,
    preview_generators: PreviewGeneratorMap = required,
    storages: StorageMap = required,
) -> str: ...
```

## Provider Setup

Supplying the implementations for each interface starts by defining
[providers](concepts.md#providers).

```python
from collections.abc import Iterator

from pybooster import provider


@provider.function
def encryptor_provider() -> Encryptor: ...


@provider.function
def preview_generators_provider() -> PreviewGeneratorMap: ...


@provider.contextmanager
def storages_provider() -> Iterator[StorageMap]: ...
```

!!! note

    The bodies of these providers will be filled in later.

These provider must then be wired together into a [solution](concepts.md#solutions).
Solutions can be relatively expensive to create, so it's best to create them once at the
start of your application and reuse them throughout its lifetime. For this, there's a
Litestar
[`lifespan` hook](https://docs.litestar.dev/2/usage/applications.html#lifespan-context-managers),
and supporting PyBooster [ASGI middleware](integrations.md#asgi-apps).

```python
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from litestar import Litestar

from pybooster import solution
from pybooster.extra.asgi import PyBoosterMiddleware


@asynccontextmanager
async def lifespan(_: Litestar) -> AsyncIterator[None]:
    with solution(encryptor_provider, preview_generators_provider, storages_provider):
        yield


app = PyBoosterMiddleware(
    # Wrap the Litestar app since it doesn't forward ASGI lifespan events to middleware
    Litestar(route_handlers=[upload], lifespan=[lifespan])
)
```

At this stage, the providers will be re-evaluated each time a request is made to the
`/upload` route. This is because no [scope](concepts.md#scopes) has been defined. In our
case there's no reason to re-evaluate the providers for each request, so you can define
a scope that will also be used for the lifespan of the application:

```python
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from litestar import Litestar

from pybooster import new_scope
from pybooster import solution
from pybooster.extra.asgi import PyBoosterMiddleware


@asynccontextmanager
async def lifespan(_: Litestar) -> AsyncIterator[None]:
    with solution(encryptor_provider, preview_generators_provider, storages_provider):
        async with new_scope(Encryptor, PreviewGeneratorMap, StorageMap):
            yield


app = PyBoosterMiddleware(
    # Wrap the Litestar app since it doesn't forward ASGI lifespan events to middleware
    Litestar(route_handlers=[upload], lifespan=[lifespan])
)
```

!!! note

    Technically you don't need to create the scope using `async with` since none of the
    providers are async, but it's good practice to do so in case you need to add async
    providers in the future. For example, establishing storage or encrytor instances
    might require a network call to perform authentication that could be made async.

## Implementing Providers

For the purposes of this tutorial the implementations can be local and mocked since the
focus is on the PyBooster integration and not the details of making a real media storage
app. As such the encryptor will be a simple XOR cipher, the preview generator mapping
will just handle PNG files, and the storage will be a save to a temporary directory.

```python
from collections.abc import Iterator
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image

from pybooster import provider


class InsecureXOREncryptor(Encryptor):
    """DO NOT USE THIS IN PRODUCTION!"""

    def __init__(self, key: bytes):
        self.key = key

    def encrypt(self, plain: bytes) -> bytes:
        return bytes([b ^ self.key[i % len(self.key)] for i, b in enumerate(plain)])

    def decrypt(self, cipher: bytes) -> bytes:
        return bytes([b ^ self.key[i % len(self.key)] for i, b in enumerate(cipher)])


@provider.function
def encryptor_provider() -> Encryptor:
    return InsecureXOREncryptor(b"secret")


class PngPreviewGenerator:
    def __init__(self, size: tuple[int, int]) -> None:
        self.size = size

    def generate(self, content: bytes) -> bytes:
        image = Image.open(BytesIO(content))
        image.thumbnail(self.size)
        output = BytesIO()
        image.save(output, format="PNG")
        return output.getvalue()


@provider.function
def preview_generators_provider() -> PreviewGeneratorMap:
    return {"image/png": PngPreviewGenerator((128, 128))}


class FileStorage(Storage):
    def __init__(self, path: Path) -> None:
        self.path = path

    async def save(self, prefix: str, data: dict[str, bytes]) -> None:
        for key, content in data.items():
            (self.path / f"{prefix}-{key}").write_bytes(content)

    async def load(self, prefix: str, keys: Collection[str]) -> dict[str, bytes]:
        return {key: (self.path / f"{prefix}-{key}").read_bytes() for key in keys}


@provider.contextmanager
def storages_provider() -> Iterator[StorageMap]:
    with TemporaryDirectory() as tempdir:
        yield {"temp": FileStorage(Path(tempdir))}
```

## Putting It All Together

With the providers in place, the `/upload` route handler should now be able to
successfully process file uploads. If you take all the code snippets from this tutorial
and put them together you should have a working media storage app:

```python
import asyncio
from base64 import b64decode
from base64 import b64encode
from collections.abc import AsyncIterator
from collections.abc import Collection
from collections.abc import Iterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Protocol
from uuid import uuid4

from asgi_lifespan import LifespanManager
from litestar import Litestar
from litestar import put
from litestar.testing import AsyncTestClient
from PIL import Image

from pybooster import injector
from pybooster import new_scope
from pybooster import provider
from pybooster import required
from pybooster import solution
from pybooster.extra.asgi import PyBoosterMiddleware

# --- PROTOCOLS ------------------------------------------------------------------------------------


class Encryptor(Protocol):
    def encrypt(self, plain: bytes) -> bytes: ...
    def decrypt(self, cipher: bytes) -> bytes: ...


class PreviewGenerator(Protocol):
    def generate(self, content: bytes) -> bytes: ...


class Storage(Protocol):
    async def save(self, prefix: str, data: dict[str, bytes]) -> None: ...
    async def load(self, prefix: str, keys: Collection[str]) -> dict[str, bytes]: ...


# --- IMPLEMENTATIONS ------------------------------------------------------------------------------


class InsecureXOREncryptor(Encryptor):
    """DO NOT USE THIS IN PRODUCTION!"""

    def __init__(self, key: bytes):
        self.key = key

    def encrypt(self, plain: bytes) -> bytes:
        return bytes([b ^ self.key[i % len(self.key)] for i, b in enumerate(plain)])

    def decrypt(self, cipher: bytes) -> bytes:
        return bytes([b ^ self.key[i % len(self.key)] for i, b in enumerate(cipher)])


@provider.function
def encryptor_provider() -> Encryptor:
    return InsecureXOREncryptor(b"secret")


class PngPreviewGenerator(PreviewGenerator):
    def __init__(self, size: tuple[int, int]) -> None:
        self.size = size

    def generate(self, content: bytes) -> bytes:
        image = Image.open(BytesIO(content))
        image.thumbnail(self.size)
        output = BytesIO()
        image.save(output, format="PNG")
        return output.getvalue()


@provider.function
def preview_generators_provider() -> PreviewGeneratorMap:
    return {"image/png": PngPreviewGenerator((128, 128))}


class FileStorage(Storage):
    def __init__(self, path: Path) -> None:
        self.path = path

    async def save(self, prefix: str, data: dict[str, bytes]) -> None:
        for key, content in data.items():
            (self.path / f"{prefix}-{key}").write_bytes(content)

    async def load(self, prefix: str, keys: Collection[str]) -> dict[str, bytes]:
        return {key: (self.path / f"{prefix}-{key}").read_bytes() for key in keys}


@provider.contextmanager
def storages_provider() -> Iterator[StorageMap]:
    with TemporaryDirectory() as tempdir:
        yield {"temp": FileStorage(Path(tempdir))}


# --- SERVER ---------------------------------------------------------------------------------------


@dataclass
class UploadData:
    content_b64: str
    content_type: str
    storage_name: str


@put("/upload")
@injector.asyncfunction(hide_signature=True)
async def upload(
    data: UploadData,
    *,
    encryptor: Encryptor = required,
    preview_generators: PreviewGeneratorMap = required,
    storages: StorageMap = required,
) -> str:
    raw = b64decode(data.content_b64)
    preview = preview_generators[data.content_type].generate(raw)

    raw_encrypted = encryptor.encrypt(raw)
    preview_encrypted = encryptor.encrypt(preview)

    prefix = uuid4().hex
    img_data = {"raw": raw_encrypted, "preview": preview_encrypted}
    await storages[data.storage_name].save(prefix, img_data)

    return prefix


@asynccontextmanager
async def lifespan(_: Litestar) -> AsyncIterator[None]:
    with solution(encryptor_provider, preview_generators_provider, storages_provider):
        async with new_scope(Encryptor, PreviewGeneratorMap, StorageMap):
            yield


app = PyBoosterMiddleware(
    Litestar(
        route_handlers=[upload],
        lifespan=[lifespan],
        debug=True,
    )
)


# --- TESTING --------------------------------------------------------------------------------------


async def main():
    fake_image_data = BytesIO()
    fake_image = Image.new("RGB", (512, 512), color="red")
    fake_image.save(fake_image_data, format="PNG")
    fake_image_data.seek(0)
    async with LifespanManager(app) as mgr, AsyncTestClient(app=mgr.app) as client:
        response = await client.put(
            "/upload",
            json={
                "content_b64": b64encode(fake_image_data.getvalue()).decode(),
                "content_type": "image/png",
                "storage_name": "temp",
            },
        )
        assert response.status_code == 200


asyncio.run(main())
```
