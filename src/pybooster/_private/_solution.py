from __future__ import annotations

from collections.abc import Callable
from collections.abc import Mapping
from collections.abc import Sequence
from collections.abc import Set
from contextvars import ContextVar
from contextvars import Token
from typing import TYPE_CHECKING
from typing import Generic
from typing import Self
from typing import TypeVar

from rustworkx import PyDiGraph
from rustworkx import descendants
from rustworkx import topological_generations

from pybooster._private._provider import ProviderInfo
from pybooster._private._provider import SyncProviderInfo
from pybooster._private._utils import frozenclass
from pybooster.types import SolutionError

if TYPE_CHECKING:

    from pybooster._private._provider import AsyncProviderInfo

P = TypeVar("P", bound=ProviderInfo)

DependencySet = set[type]
DependencyMap = Mapping[type, DependencySet]


def set_solutions(
    sync_infos: Mapping[type, SyncProviderInfo],
    async_infos: Mapping[type, AsyncProviderInfo],
) -> Callable[[], None]:

    full_infos = {**sync_infos, **async_infos}

    sync_solution_token = _set_solution(SYNC_SOLUTION, sync_infos)
    full_solution_token = _set_solution(FULL_SOLUTION, full_infos)

    def reset() -> None:
        FULL_SOLUTION.reset(full_solution_token)
        SYNC_SOLUTION.reset(sync_solution_token)

    return reset


def _set_solution(var: ContextVar[Solution[P]], infos: Mapping[type, P]) -> Token[Solution[P]]:
    dep_map = {cls: info["dependencies"] for cls, info in infos.items()}
    return var.set(Solution(infos=infos, graph=DependencyGraph.from_dependency_map(dep_map)))


@frozenclass
class Solution(Generic[P]):
    """A solution to the dependency graph."""

    infos: Mapping[type, P]
    graph: DependencyGraph

    def descendant_types(self, cls: type) -> Set[type]:
        graph = self.graph
        return {graph.type_by_index[i] for i in descendants(graph.index_graph, graph.index_by_type[cls])}

    def execution_order_for(self, types: Set[type]) -> Sequence[Sequence[P]]:
        infos = self.infos
        return [[infos[t] for t in union] for gen in self.graph.type_ordering if (union := types & gen)]


@frozenclass
class DependencyGraph:

    type_by_index: Mapping[int, type]
    """Mapping graph index to types."""
    type_ordering: Sequence[Set[type]]
    r"""Topologically sorted generations of type IDs."""
    index_by_type: Mapping[type, int]
    """Mapping types to graph index."""
    index_graph: PyDiGraph
    """A directed graph of type IDs."""

    @classmethod
    def from_dependency_map(cls, dep_map: Mapping[type, Set[type]]) -> Self:
        type_by_index: dict[int, type] = {}
        index_by_type: dict[type, int] = {}

        index_graph = PyDiGraph()
        for tp in dep_map:
            index = index_graph.add_node(tp)
            type_by_index[index] = tp
            index_by_type[tp] = index

        for tp, deps in dep_map.items():
            for dep in deps:
                try:
                    parent_index = index_by_type[dep]
                except KeyError:
                    msg = f"No provider for {dep}"
                    raise SolutionError(msg) from None
                child_index = index_by_type[tp]
                index_graph.add_edge(parent_index, child_index, None)

        return cls(
            type_by_index=type_by_index,
            index_by_type=index_by_type,
            index_graph=index_graph,
            type_ordering=[{type_by_index[i] for i in gen} for gen in topological_generations(index_graph)],
        )


_NO_SOLUTION = Solution(infos={}, graph=DependencyGraph.from_dependency_map({}))
SYNC_SOLUTION = ContextVar[Solution[SyncProviderInfo]]("SYNC_SOLUTION", default=_NO_SOLUTION)
FULL_SOLUTION = ContextVar[Solution[ProviderInfo]]("FULL_SOLUTION", default=_NO_SOLUTION)
