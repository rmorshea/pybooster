from __future__ import annotations

from collections.abc import Sequence
from contextlib import contextmanager
from typing import TYPE_CHECKING
from typing import Any

from pybooster.core._private._provider import AsyncProviderInfo
from pybooster.core._private._provider import SyncProviderInfo
from pybooster.core._private._provider import get_provider_info
from pybooster.core._private._solution import set_solution
from pybooster.core.provider import Provider
from pybooster.core.provider import SyncProvider

if TYPE_CHECKING:
    from collections.abc import Iterator


@contextmanager
def solution(*providers: Provider[[], Any] | Sequence[Provider[[], Any]]) -> Iterator[None]:
    """Resolve the dependencies between the given providers and use them for the duration of the context."""
    sync_infos: dict[type, SyncProviderInfo] = {}
    async_infos: dict[type, AsyncProviderInfo] = {}
    for p in _normalize_providers(providers):
        if isinstance(p, SyncProvider):
            sync_infos.update(get_provider_info(p.producer, p.provides, p.dependencies, is_sync=True))
        else:
            async_infos.update(get_provider_info(p.producer, p.provides, p.dependencies, is_sync=False))
    reset = set_solution(sync_infos, async_infos)
    try:
        yield
    finally:
        reset()


def _normalize_providers(
    providers: Sequence[Provider[[], Any] | Sequence[Provider[[], Any]]],
) -> Sequence[Provider[[], Any]]:
    normalized: list[Provider[[], Any]] = []
    for p in providers:
        if isinstance(p, Sequence):
            normalized.extend(p)
        else:
            normalized.append(p)
    return normalized
