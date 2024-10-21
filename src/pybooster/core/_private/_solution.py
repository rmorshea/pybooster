from __future__ import annotations

from collections.abc import Mapping
from collections.abc import Sequence
from contextvars import ContextVar
from contextvars import Token
from graphlib import TopologicalSorter
from typing import TYPE_CHECKING
from typing import Callable
from typing import TypeVar

from pybooster.core._private._provider import ProviderInfo
from pybooster.core._private._provider import SyncProviderInfo

if TYPE_CHECKING:

    from pybooster.core._private._provider import AsyncProviderInfo
    from pybooster.core._private._provider import NormDependencies

Graph = Mapping[type, set[type]]
NodeSet = set[type]

P = TypeVar("P", bound=ProviderInfo)


def get_sync_solution(dependencies: NormDependencies) -> Sequence[Sequence[SyncProviderInfo]]:
    return _get_solution(_SYNC_INFOS, _SYNC_SOLUTION, dependencies)


def get_full_solution(dependencies: NormDependencies) -> Sequence[Sequence[ProviderInfo]]:
    return _get_solution(_FULL_INFOS, _FULL_SOLUTION, dependencies)


def _get_solution(
    infos_var: ContextVar[P],
    solution_var: ContextVar[Solution],
    dependencies: NormDependencies,
) -> Sequence[Sequence[P]]:
    infos = infos_var.get()
    solution = solution_var.get()

    node_sets: list[NodeSet] = []
    for dep_options in dependencies.values():
        for d in dep_options:
            if s := solution.get(d):
                node_sets.append(s)
                break
        else:
            msg = f"Missing providers for any of {dep_options}"
            raise RuntimeError(msg)

    return [(infos[cls] for cls in group) for sparse_groups in zip(*node_sets) if (group := set.union(*sparse_groups))]


def set_solution(
    sync_infos: Mapping[type, SyncProviderInfo],
    async_infos: Mapping[type, AsyncProviderInfo],
) -> Callable[[], None]:
    full_infos = {**sync_infos, **async_infos}

    sync_infos_token = _SYNC_INFOS.set(sync_infos)
    full_infos_token = _FULL_INFOS.set(full_infos)
    sync_solution_token = _set_solution(_SYNC_SOLUTION, sync_infos)
    full_solution_token = _set_solution(_FULL_SOLUTION, full_infos)

    def reset() -> None:
        _FULL_SOLUTION.reset(full_solution_token)
        _SYNC_SOLUTION.reset(sync_solution_token)
        _FULL_INFOS.reset(full_infos_token)
        _SYNC_INFOS.reset(sync_infos_token)

    return reset


def _set_solution(var: ContextVar, infos: Mapping[type, ProviderInfo]) -> Token:
    graph = {provides: info["dependencies"] for provides, info in infos.items()}
    all_sorted_groups = _get_sorted_groups(graph)
    return var.set(
        {
            provides: _intersect_sorted_groups(all_sorted_groups, _nodes_in_subgraph(graph, provides))
            for provides in graph
        }
    )


def _get_sorted_groups(graph: Graph) -> Sequence[NodeSet]:
    sorter = TopologicalSorter(graph)
    sorter.prepare()
    sorted_groups: list[set[type]] = []
    while sorter.is_active():
        group = sorter.get_ready()
        sorted_groups.append(set(group))
        sorter.done(*group)
    return sorted_groups


def _intersect_sorted_groups(groups: Sequence[NodeSet], subset: set[type]) -> Sequence[NodeSet]:
    return [subset.intersection(g) for g in groups]


def _nodes_in_subgraph(graph: Graph, root: type) -> set[type]:
    index = 0
    visit = [root]
    while index < len(visit):
        node = visit[index]
        if node in graph:
            visit.extend(graph[node])
        index += 1
    return set(visit)


Solution = Mapping[type, Sequence[NodeSet]]
_SYNC_INFOS = ContextVar[Mapping[type, SyncProviderInfo]]("SYNC_INFOS")
_FULL_INFOS = ContextVar[Mapping[type, ProviderInfo]]("FULL_INFOS")
_SYNC_SOLUTION = ContextVar[Solution]("SYNC_SOLUTION")
_FULL_SOLUTION = ContextVar[Solution]("FULL_SOLUTION")
