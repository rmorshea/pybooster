__version__ = "0.0.5b1"

from ninject._private.inspect import default
from ninject._private.inspect import required
from ninject.core.current import Current
from ninject.core.inject import inject
from ninject.core.let import let
from ninject.core.provider import Provider
from ninject.core.provider import provider

__all__ = ("Current", "Provider", "default", "inject", "let", "provider", "required")
