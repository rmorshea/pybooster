from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from typing import Any
from typing import TypedDict

from pybooster.core.state import copy_state

if TYPE_CHECKING:
    from collections.abc import Awaitable
    from collections.abc import Callable
    from collections.abc import MutableMapping

    from pybooster.core.state import StateSetter

    Scope = MutableMapping[str, Any]
    Message = MutableMapping[str, Any]
    Receive = Callable[[], Awaitable[Message]]
    Send = Callable[[Message], Awaitable[None]]
    Asgi = Callable[[Scope, Receive, Send], Awaitable[None]]

log = logging.getLogger(__name__)


class PyBoosterMiddleware:
    """ASGI middleware to manage PyBooster's internal state."""

    def __init__(self, app: Asgi) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:  # noqa: D102
        if scope["type"] == "lifespan":

            async def send_wrapper(msg: MutableMapping[str, Any]) -> None:
                if msg["type"] == "lifespan.startup.complete":
                    _set_scope_state(scope, {"set_state": copy_state()})
                await send(msg)

            await self.app(scope, receive, send_wrapper)

        elif (state := _get_scope_state(scope)) is not None:
            state["set_state"]()
            await self.app(scope, receive, send)
        else:  # nocov
            msg = "PyBooster's internal state is missing."
            raise RuntimeError(msg)


def _set_scope_state(scope: Scope, state: _ScopeState) -> None:
    try:
        scope["state"][_SCOPE_STATE_NAME] = state
    except KeyError:  # nocov
        msg = "Server does not support lifespan state."
        raise RuntimeError(msg) from None


def _get_scope_state(scope: Scope) -> _ScopeState | None:
    try:
        return scope["state"].get(_SCOPE_STATE_NAME)
    except KeyError:  # nocov
        msg = "Server does not support lifespan state."
        raise RuntimeError(msg) from None


class _ScopeState(TypedDict):
    set_state: StateSetter


_SCOPE_STATE_NAME = "pybooster"
