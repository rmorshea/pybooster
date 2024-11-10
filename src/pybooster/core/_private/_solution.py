from __future__ import annotations

from collections.abc import Mapping
from collections.abc import Sequence
from contextvars import ContextVar
from contextvars import Token
from logging import getLogger
from typing import TYPE_CHECKING
from typing import Callable
from typing import Generic
from typing import TypeVar

from rustworkx import PyDiGraph
from rustworkx import topological_generations

from pybooster.core._private._provider import ProviderInfo
from pybooster.core._private._provider import SyncProviderInfo
from pybooster.types import ProviderMissingError

if TYPE_CHECKING:

    from pybooster.core._private._provider import AsyncProviderInfo
    from pybooster.core._private._provider import NormParamTypes

P = TypeVar("P", bound=ProviderInfo)

DependencySet = set[type]
DependencyMap = Mapping[type, DependencySet]


_log = getLogger(__name__)


def get_sync_solution(required_params: NormParamTypes) -> Sequence[Sequence[SyncProviderInfo]]:
    return _get_solution(_SYNC_SOLUTION.get(), tuple(required_params.values()))


def get_full_solution(required_params: NormParamTypes) -> Sequence[Sequence[ProviderInfo]]:
    return _get_solution(_FULL_SOLUTION.get(), tuple(required_params.values()))


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

    node_sets: list[DependencySet] = []
    for dep_options in dependencies:
        for d in dep_options:
            if s := execution_orders.get(d):
                node_sets.append(s)
                break
        else:
            _log.debug(f"Missing providers for any of {list(dep_options)}")

    return [[infos[cls] for cls in g] for sparse_gens in zip(*node_sets) if (g := set.union(*sparse_gens))]


def _set_solution(var: ContextVar[_Solution[P]], infos: Mapping[type, P]) -> Token:
    dep_map = {cls: info["dependencies"] for cls, info in infos.items()}
    _check_all_requirements_exist(var, dep_map)
    sorted_gens = _get_sorted_generations(dep_map)
    exe_orders = {cls: _intersect_sorted_generations(sorted_gens, _nodes_in_subgraph(dep_map, cls)) for cls in dep_map}
    return var.set(_Solution(infos, exe_orders))


def _get_sorted_generations(dep_map: DependencyMap) -> Sequence[DependencySet]:
    graph = PyDiGraph()

    types_by_node_id: dict[int, type] = {}
    node_ids_by_type: dict[type, int] = {}
    for cls in dep_map:
        node_id = graph.add_node(cls)
        types_by_node_id[node_id] = cls
        node_ids_by_type[cls] = node_id

    for cls, deps in dep_map.items():
        for dep in deps:
            graph.add_edge(node_ids_by_type[dep], node_ids_by_type[cls], None)

    return [[types_by_node_id[node_id] for node_id in gen] for gen in topological_generations(graph)]


def _check_all_requirements_exist(var: ContextVar, dep_map: DependencyMap) -> None:
    any_missing: set[type] = set()
    for requirements in dep_map.values():
        if some_missing := requirements - dep_map.keys():
            any_missing.update(some_missing)
    if any_missing:
        sync = "sync" if var is _SYNC_SOLUTION else "sync or async"
        msg = f"No {sync} providers for {any_missing}"
        raise ProviderMissingError(msg)


def _intersect_sorted_generations(generations: Sequence[DependencySet], subset: set[type]) -> Sequence[DependencySet]:
    return [subset.intersection(g) for g in generations]


def _nodes_in_subgraph(graph: DependencyMap, root: type) -> set[type]:
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
        execution_orders: Mapping[type, Sequence[DependencySet]],
    ) -> None:
        self.infos_by_type = infos_by_type
        self.execution_orders = execution_orders


_NO_SOLUTION = _Solution({}, {})
_SYNC_SOLUTION = ContextVar[_Solution[SyncProviderInfo]]("SYNC_SOLUTION", default=_NO_SOLUTION)
_FULL_SOLUTION = ContextVar[_Solution[ProviderInfo]]("FULL_SOLUTION", default=_NO_SOLUTION)
