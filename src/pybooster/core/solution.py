from __future__ import annotations

from collections.abc import Sequence
from contextlib import contextmanager
from typing import TYPE_CHECKING
from typing import Any

from pybooster._private._provider import AsyncProviderInfo
from pybooster._private._provider import SyncProviderInfo
from pybooster._private._provider import get_provider_info
from pybooster._private._solution import set_solutions
from pybooster.core import provider
from pybooster.core.injector import _CURRENT_VALUES
from pybooster.core.provider import Provider
from pybooster.core.provider import SyncProvider

if TYPE_CHECKING:
    from collections.abc import Iterator


@contextmanager
def solved(*providers: Provider[[], Any] | Sequence[Provider[[], Any]]) -> Iterator[None]:
    """Resolve the dependency graph defined by the given providers during the context.

    Args:
        providers:
            The providers that define the dependency graph to be resolved given
            as positional arguments or as sequences of providers.
    """
    if not providers:
        msg = "At least one provider must be given."
        raise ValueError(msg)
    sync_infos: dict[type, SyncProviderInfo] = {}
    async_infos: dict[type, AsyncProviderInfo] = {}
    for p in [
        *_implicit_providers_from_current_values(),
        *_normalize_providers(providers),
    ]:
        if isinstance(p, SyncProvider):
            sync_infos.update(
                get_provider_info(p.producer, p.provides, p.dependencies, is_sync=True)
            )
        else:
            async_infos.update(
                get_provider_info(p.producer, p.provides, p.dependencies, is_sync=False)
            )
    reset = set_solutions(sync_infos, async_infos)
    try:
        yield
    finally:
        reset()


def _implicit_providers_from_current_values() -> list[Provider[[], Any]]:
    return [
        provider.function(lambda val=val: val, provides=cls)
        for cls, val in _CURRENT_VALUES.get().items()
    ]


def _normalize_providers(
    providers: Sequence[Provider[[], Any] | Sequence[Provider[[], Any]]],
) -> Sequence[Provider[[], Any]]:
    normalized: list[Provider[[], Any]] = []
    for p in providers:
        normalized.extend(p) if isinstance(p, Sequence) else normalized.append(p)
    return normalized
