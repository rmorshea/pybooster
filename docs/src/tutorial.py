from base64 import b64decode
from collections.abc import AsyncIterator
from collections.abc import Collection
from collections.abc import Iterator
from collections.abc import Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Protocol
from uuid import uuid4

from litestar import Litestar
from litestar import put
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
def preview_generators_provider() -> Mapping[str, PreviewGenerator]:
    return {"image/png": PngPreviewGenerator((128, 128))}


class FileStorage(Storage):
    def __init__(self, path: Path) -> None:
        self.path = path

    async def save(self, prefix: str, data: dict[str, bytes]) -> None:
        for key, content in data.items():
            (self.path / prefix / key).write_bytes(content)

    async def load(self, prefix: str, keys: Collection[str]) -> dict[str, bytes]:
        return {key: (self.path / prefix / key).read_bytes() for key in keys}


@provider.contextmanager
def storages_provider() -> Iterator[Mapping[str, Storage]]:
    with TemporaryDirectory() as tempdir:
        yield {"temp": FileStorage(Path(tempdir))}


# --- SERVER ---------------------------------------------------------------------------------------


@dataclass
class UploadRequest:
    content_b64: str
    content_type: str
    storage_name: str


@put("/upload")
@injector.asyncfunction
async def upload(
    request: UploadRequest,
    *,
    encryptor: Encryptor = required,
    preview_generators: Mapping[str, PreviewGenerator] = required,
    storages: Mapping[str, Storage] = required,
) -> str:
    raw = b64decode(request.content_b64)
    preview = preview_generators[request.content_type].generate(raw)

    raw_encrypted = encryptor.encrypt(raw)
    preview_encrypted = encryptor.encrypt(preview)

    prefix = uuid4().hex
    data = {"raw": raw_encrypted, "preview": preview_encrypted}
    await storages[request.storage_name].save(prefix, data)

    return prefix


@asynccontextmanager
async def lifespan(_: Litestar) -> AsyncIterator[None]:
    with solution(encryptor_provider, preview_generators_provider, storages_provider):
        async with new_scope(Encryptor, Mapping[str, PreviewGenerator], Mapping[str, Storage]):
            yield


app = Litestar(route_handlers=[upload], lifespan=[lifespan], middleware=[PyBoosterMiddleware])
