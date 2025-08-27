from importlib.metadata import PackageNotFoundError
from importlib.metadata import version

from pybooster.core import injector
from pybooster.core import provider
from pybooster.core.injector import required
from pybooster.core.scope import Scope
from pybooster.core.scope import get_scope
from pybooster.core.scope import new_scope
from pybooster.core.solution import solution

try:
    __version__ = version(__name__)
except PackageNotFoundError:  # nocov
    __version__ = "0.0.0"

__all__ = (
    "Scope",
    "get_scope",
    "injector",
    "new_scope",
    "provider",
    "required",
    "solution",
)
