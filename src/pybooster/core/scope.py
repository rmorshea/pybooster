from __future__ import annotations

from collections.abc import Mapping
from contextlib import AbstractAsyncContextManager
from contextlib import AbstractContextManager
from typing import Any
from typing import cast

from typing_extensions import TypeVar

from pybooster._private._injector import _CURRENT_VALUES
from pybooster._private._injector import async_inject_into_params
from pybooster._private._injector import sync_inject_into_params
from pybooster._private._utils import AsyncFastStack
from pybooster._private._utils import FastStack
from pybooster.types import Hint

R = TypeVar("R")
N = TypeVar("N", default=None)


def new_scope(*args: Hint | Mapping[Hint, Any]) -> _ScopeContext:
    """Share the values for a set of dependencies for the duration of a context."""
    param_vals: dict[str, Any] = {}
    param_deps: dict[str, Hint] = {}
    index = 0
    for arg in args:
        match arg:
            case Mapping():
                for cls, val in arg.items():
                    key = f"__{index}"
                    param_vals[key] = val
                    param_deps[key] = cls
                    index += 1
            case cls:
                param_deps[f"__{index}"] = cls
                index += 1
    return _ScopeContext(param_vals, param_deps)


def get_scope() -> Scope:
    """Get a mapping from dependency types to their current values."""
    return cast("Scope", dict(_CURRENT_VALUES.get()))


class Scope(Mapping[Hint, Any]):
    """A mapping from dependency types to their current values."""

    def __getitem__(self, key: type[R]) -> R: ...  # nocov
    def get(self, key: type[R], default: N = ...) -> R | N: ...  # nocov # noqa: D102


class _ScopeContext(AbstractContextManager[Scope], AbstractAsyncContextManager[Scope]):
    def __init__(
        self,
        param_vals: dict[str, Any],
        param_deps: dict[str, type],
    ) -> None:
        self._param_vals = param_vals
        self._param_deps = param_deps

    def __enter__(self) -> Scope:
        if hasattr(self, "_sync_stack"):
            msg = "Cannot reuse a context manager."
            raise RuntimeError(msg)
        self._sync_stack = FastStack()
        params = self._param_vals.copy()
        sync_inject_into_params(
            self._sync_stack,
            params,
            self._param_deps,
            set_scope=True,
        )
        return cast("Scope", {self._param_deps[k]: v for k, v in params.items()})

    def __exit__(self, *_: Any) -> None:
        try:
            self._sync_stack.close()
        finally:
            del self._sync_stack

    async def __aenter__(self) -> Scope:
        if hasattr(self, "_async_stack"):
            msg = "Cannot reuse a context manager."
            raise RuntimeError(msg)
        self._async_stack = AsyncFastStack()
        params = self._param_vals.copy()
        await async_inject_into_params(
            self._async_stack,
            params,
            self._param_deps,
            set_scope=True,
        )
        return cast("Scope", {self._param_deps[k]: v for k, v in params.items()})

    async def __aexit__(self, *exc: Any) -> None:
        try:
            await self._async_stack.aclose()
        finally:
            del self._async_stack
