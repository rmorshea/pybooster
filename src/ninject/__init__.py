__version__ = "0.0.1"

from ninject.core import Context, inject
from ninject.types import AnyProvider, Dependency, dependencies

__all__ = (
    "AnyProvider",
    "Dependency",
    "dependencies",
    "inject",
    "Context",
)
