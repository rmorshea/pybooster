from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from contextlib import AbstractContextManager
from contextlib import AsyncExitStack
from contextlib import ExitStack
from functools import wraps
from typing import TYPE_CHECKING
from typing import Any
from typing import Callable
from typing import ParamSpec
from typing import TypeVar

from ninject._private.injector import async_enter_provider_context
from ninject._private.injector import sync_enter_provider_context
from ninject._private.injector import update_dependency_values
from ninject._private.provider import ASYNC_PROVIDER_INFOS as _ASYNC_PROVIDER_INFOS
from ninject._private.provider import SYNC_PROVIDER_INFOS as _SYNC_PROVIDER_INFOS
from ninject._private.provider import AsyncProviderInfo
from ninject._private.provider import SyncProviderInfo

if TYPE_CHECKING:
    from collections.abc import Awaitable
    from collections.abc import Coroutine
    from collections.abc import Mapping

P = ParamSpec("P")
R = TypeVar("R")


def function(func: Callable[P, R]) -> Callable[P, R]:
    """Activate all singleton providers before calling the function."""

    @wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        with Context():
            return func(*args, **kwargs)

    return wrapper


def asyncfunction(func: Callable[P, Awaitable[R]]) -> Callable[P, Coroutine[None, None, R]]:
    """Activate all singleton providers before calling the coroutine."""

    @wraps(func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        async with Context():
            return await func(*args, **kwargs)

    return wrapper


def context() -> Context:
    """Create a context manager that activates all singleton providers."""
    return Context(
        {c: p for c, p in _SYNC_PROVIDER_INFOS.get().items() if p["singleton"]},
        {c: p for c, p in _ASYNC_PROVIDER_INFOS.get().items() if p["singleton"]},
    )


class Context(AbstractContextManager[None], AbstractAsyncContextManager[None]):
    """A context manager that activates all singleton providers."""

    def __init__(
        self,
        sync_singleton_provider_infos: Mapping[type, SyncProviderInfo],
        async_singleton_provider_infos: Mapping[type, AsyncProviderInfo],
    ):
        self._sync_provider_infos = sync_singleton_provider_infos
        self._async_provider_infos = async_singleton_provider_infos

    def __enter__(self) -> None:
        if hasattr(self, "_sync_stack"):
            msg = "Context is not re-entrant"
            raise RuntimeError(msg)
        stack = self._sync_stack = ExitStack()
        new_dependency_values: dict[type, Any] = {}
        for cls, provider in self._sync_provider_infos.items():
            new_dependency_values[cls] = sync_enter_provider_context(stack, provider)
        update_dependency_values(stack, new_dependency_values)

    def __exit__(self, *exc_info) -> None:
        try:
            self._sync_stack.__exit__(*exc_info)
        finally:
            del self._sync_stack

    async def __aenter__(self) -> None:
        if hasattr(self, "_async_stack"):
            msg = "Context is not re-entrant"
            raise RuntimeError(msg)
        stack = self._async_stack = AsyncExitStack()
        new_dependency_values: dict[type, Any] = {}
        for cls, provider in self._sync_provider_infos.items():
            new_dependency_values[cls] = sync_enter_provider_context(stack, provider)
        for cls, provider in self._async_provider_infos.items():
            new_dependency_values[cls] = await async_enter_provider_context(stack, provider)
        update_dependency_values(stack, new_dependency_values)

    async def __aexit__(self, *exc_info) -> None:
        try:
            await self._async_stack.__aexit__(*exc_info)
        finally:
            del self._async_stack
