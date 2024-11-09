from __future__ import annotations

from collections.abc import Mapping
from collections.abc import Sequence
from contextvars import ContextVar
from contextvars import Token
from graphlib import TopologicalSorter
from logging import getLogger
from typing import TYPE_CHECKING
from typing import Callable
from typing import Generic
from typing import TypeVar

from pybooster.core._private._provider import ProviderInfo
from pybooster.core._private._provider import SyncProviderInfo
from pybooster.core.types import ProviderMissingError

if TYPE_CHECKING:

    from pybooster.core._private._provider import AsyncProviderInfo
    from pybooster.core._private._provider import NormDependencies

P = TypeVar("P", bound=ProviderInfo)

Graph = Mapping[type, set[type]]
NodeSet = set[type]

_log = getLogger(__name__)


def get_sync_solution(dependencies: NormDependencies) -> Sequence[Sequence[SyncProviderInfo]]:
    return _get_solution(_SYNC_SOLUTION.get(), tuple(dependencies.values()))


def get_full_solution(dependencies: NormDependencies) -> Sequence[Sequence[ProviderInfo]]:
    return _get_solution(_FULL_SOLUTION.get(), tuple(dependencies.values()))


def set_solution(
    sync_infos: Mapping[type, SyncProviderInfo],
    async_infos: Mapping[type, AsyncProviderInfo],
) -> Callable[[], None]:

    full_infos = {**sync_infos, **async_infos}

    sync_solution_token = _set_solution(_SYNC_SOLUTION, sync_infos)
    full_solution_token = _set_solution(_FULL_SOLUTION, full_infos)

    def reset() -> None:
        _FULL_SOLUTION.reset(full_solution_token)
        _SYNC_SOLUTION.reset(sync_solution_token)

    return reset


def _get_solution(
    solution: _Solution[P],
    dependencies: Sequence[Sequence[type]],
) -> Sequence[Sequence[P]]:
    infos = solution.infos_by_type
    execution_orders = solution.execution_orders

    node_sets: list[NodeSet] = []
    for dep_options in dependencies:
        for d in dep_options:
            if s := execution_orders.get(d):
                node_sets.append(s)
                break
        else:
            _log.debug(f"Missing providers for any of {list(dep_options)}")

    return [[infos[cls] for cls in group] for sparse_groups in zip(*node_sets) if (group := set.union(*sparse_groups))]


def _set_solution(var: ContextVar[_Solution[P]], infos: Mapping[type, P]) -> Token:
    graph = {provides: info["dependencies"] for provides, info in infos.items()}
    _check_all_dependencies_exist(var, graph)
    all_sorted_groups = _get_sorted_groups(graph)
    exe_orders = {cls: _intersect_sorted_groups(all_sorted_groups, _nodes_in_subgraph(graph, cls)) for cls in graph}
    return var.set(_Solution(infos, exe_orders))


def _get_sorted_groups(graph: Graph) -> Sequence[NodeSet]:
    sorter = TopologicalSorter(graph)
    sorter.prepare()
    sorted_groups: list[set[type]] = []
    while sorter.is_active():
        group = sorter.get_ready()
        sorted_groups.append(set(group))
        sorter.done(*group)
    return sorted_groups


def _check_all_dependencies_exist(var: ContextVar, graph: Graph) -> None:
    any_missing: set[type] = set()
    for dependencies in graph.values():
        if some_missing := dependencies - graph.keys():
            any_missing.update(some_missing)
    if any_missing:
        sync = "sync" if var is _SYNC_SOLUTION else "sync or async"
        msg = f"No {sync} providers for {any_missing}"
        raise ProviderMissingError(msg)


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


class _Solution(Generic[P]):

    def __init__(
        self,
        infos_by_type: Mapping[type, SyncProviderInfo],
        execution_orders: Mapping[type, Sequence[NodeSet]],
    ) -> None:
        self.infos_by_type = infos_by_type
        self.execution_orders = execution_orders


_NO_SOLUTION = _Solution({}, {})
_SYNC_SOLUTION = ContextVar[_Solution[SyncProviderInfo]]("SYNC_SOLUTION", default=_NO_SOLUTION)
_FULL_SOLUTION = ContextVar[_Solution[ProviderInfo]]("FULL_SOLUTION", default=_NO_SOLUTION)
