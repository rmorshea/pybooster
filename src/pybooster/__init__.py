from importlib.metadata import PackageNotFoundError
from importlib.metadata import version

from pybooster.core import injector
from pybooster.core import provider
from pybooster.core.injector import required
from pybooster.core.solution import solved

try:
    __version__ = version(__name__)
except PackageNotFoundError:  # nocov
    __version__ = "0.0.0"

__all__ = (
    "injector",
    "provider",
    "required",
    "solved",
)
