from __future__ import annotations

from collections.abc import Callable
from collections.abc import Collection
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
from rustworkx import ancestors
from rustworkx import descendants
from rustworkx import topological_generations

from pybooster._private._provider import ProviderInfo
from pybooster._private._provider import SyncProviderInfo
from pybooster._private._utils import frozenclass
from pybooster.types import Hint
from pybooster.types import InjectionError
from pybooster.types import SolutionError

if TYPE_CHECKING:
    from pybooster._private._provider import AsyncProviderInfo

P = TypeVar("P", bound=ProviderInfo)

DependencySet = Set[Hint]
DependencyMap = Mapping[Hint, DependencySet]


def set_solutions(
    sync_infos: Mapping[Hint, SyncProviderInfo],
    async_infos: Mapping[Hint, AsyncProviderInfo],
) -> Callable[[], None]:
    full_infos = {**sync_infos, **async_infos}

    sync_solution_token = _set_solution(SYNC_SOLUTION, sync_infos)
    full_solution_token = _set_solution(FULL_SOLUTION, full_infos)

    def reset() -> None:
        FULL_SOLUTION.reset(full_solution_token)
        SYNC_SOLUTION.reset(sync_solution_token)

    return reset


def _set_solution(var: ContextVar[Solution[P]], infos: Mapping[Hint, P]) -> Token[Solution[P]]:
    dep_map = {cls: set(info["required_parameters"].values()) for cls, info in infos.items()}
    return var.set(Solution.from_infos_and_dependency_map(infos, dep_map))


@frozenclass
class Solution(Generic[P]):
    """A solution to the dependency graph."""

    type_by_index: Mapping[int, Hint]
    """Mapping graph index to types."""
    index_ordering: Sequence[Set[int]]
    r"""Topologically sorted generations of type IDs."""
    index_by_type: Mapping[Hint, int]
    """Mapping types to graph index."""
    index_graph: PyDiGraph
    """A directed graph of type IDs."""
    infos_by_index: Mapping[int, P]
    """Mapping graph index to provider infos."""
    infos_by_type: Mapping[Hint, P]
    """Mapping types to provider infos."""

    @classmethod
    def from_infos_and_dependency_map(
        cls, infos_by_type: Mapping[Hint, P], deps_by_type: DependencyMap
    ) -> Self:
        type_by_index: dict[int, Hint] = {}
        index_by_type: dict[Hint, int] = {}

        index_graph = PyDiGraph()
        for tp in deps_by_type:
            index = index_graph.add_node(tp)
            type_by_index[index] = tp
            index_by_type[tp] = index

        infos_by_index = {index_by_type[tp]: info for tp, info in infos_by_type.items()}

        for tp, deps in deps_by_type.items():
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
            index_ordering=[set(gen) for gen in topological_generations(index_graph)],
            infos_by_index=infos_by_index,
            infos_by_type=infos_by_type,
        )

    def descendant_types(self, cls: Hint) -> Set[Hint]:
        type_by_index = self.type_by_index  # avoid extra attribute accesses
        if cls not in self.index_by_type:
            return set()
        return {type_by_index[i] for i in descendants(self.index_graph, self.index_by_type[cls])}

    def execution_order_for(
        self, include_types: Collection[Hint], exclude_types: Collection[Hint]
    ) -> Sequence[Sequence[P]]:
        index_by_type = self.index_by_type  # avoid extra attribute accesses
        try:
            type_indices = {index_by_type[t] for t in include_types}
        except KeyError:
            missing = set(include_types) - set(index_by_type)
            msg = f"Missing providers for {missing}"
            raise InjectionError(msg) from None
        ancestor_indices = {p_i for i in type_indices for p_i in ancestors(self.index_graph, (i))}
        ancestor_pred_indices = ancestor_indices | type_indices

        filter_indicies = {index_by_type[t] for t in exclude_types}
        infos = self.infos_by_index  # avoid extra attribute accesses
        return [
            [infos[i] for i in union]
            for gen in self.index_ordering
            if (union := (gen & ancestor_pred_indices - filter_indicies))
        ]


_NO_SOLUTION = Solution.from_infos_and_dependency_map({}, {})
SYNC_SOLUTION = ContextVar[Solution[SyncProviderInfo]]("SYNC_SOLUTION", default=_NO_SOLUTION)
FULL_SOLUTION = ContextVar[Solution[ProviderInfo]]("FULL_SOLUTION", default=_NO_SOLUTION)
