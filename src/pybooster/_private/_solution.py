from __future__ import annotations

from collections.abc import Callable
from collections.abc import Collection
from collections.abc import Mapping
from collections.abc import Sequence
from collections.abc import Set
from contextvars import ContextVar
from contextvars import Token
from itertools import starmap
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

    def execution_order_for(self, types: Collection[type]) -> Sequence[Sequence[P]]:
        infos = self.infos
        i_by_t = self.graph.index_by_type
        t_by_i = self.graph.type_by_index

        sparse_topo_generations = [self.graph.index_sparse_topological_ancestor_generations[i_by_t[c]] for c in types]
        merged_topo_generations = list(starmap(set.union, zip(*sparse_topo_generations, strict=True)))

        return [[infos[t_by_i[i]] for i in gen] for gen in merged_topo_generations]


@frozenclass
class DependencyGraph:

    type_by_index: Mapping[int, type]
    """Mapping graph index to types."""
    index_by_type: Mapping[type, int]
    """Mapping types to graph index."""
    index_graph: PyDiGraph
    """A directed graph of type IDs."""
    index_sparse_topological_ancestor_generations: Mapping[int, Sequence[Set[int]]]
    r"""Topologically sorted generations where generations have been intersected with each node and its ancestors.

    For example, given the graph (directed from top to bottom)

    ```
        0
       / \
      1   2
     / \   \
    3   4   5
    ```

    The topological generations for the whole graph would be:

    ```
    topological_generations = [{0}, {1, 2}, {3, 4, 5}]
    ```

    And the ancestors (inclusive) for each node would be:

    ```python
    inclusive_ancestors = {
        0: {0},
        1: {0, 1},
        2: {0, 2},
        3: {0, 1, 3},
        4: {0, 1, 4},
        5: {0, 2, 5},
    }
    ```

    If we define sparse topological generations with the following code:

    ```python
    def get_sparse_topological_generations(
        topological_generations, inclusive_ancestors
    ):
        return [
            {gen & inclusive_ancestors[i] for i in gen}
            for gen in topological_generations
        ]
    ```

    Then the sparse topological generations for node 4 would be:

    ```
    [{0}, {1}, {4}]
    ```

    That is, the each generation, but only node 4 and its ancestors. Thus, for all nodes, the generations are

    ```python
    {
        0: [{0}, set(), set()],
        1: [{0}, {1}, set()],
        2: [{0}, {2}, set()],
        3: [{0}, {1}, {3}],
        4: [{0}, {1}, {4}],
        5: [{0}, {2}, {5}],
    }
    ```

    This makes it easy to construct the topological generations for arbitrary ancestral subgraphs. For example, if we
    wanted the topological generations for the ancestral subgraphs of node 4 and 5. We would take the union of their
    sparse generations:

    ```python
    from itertools import starmap

    sparse_gens_4 = [{0}, {1}, {4}]
    sparse_gens_5 = [{0}, {2}, {5}]
    merged_gens = list(
        starmap(set.union, zip(sparse_gens_4, sparse_gens_5, strict=False))
    )
    assert merged_gens == [{0}, {1, 2}, {4, 5}]
    ```
    """

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

        topological_id_generations = [set(gen) for gen in topological_generations(index_graph)]

        sparse_generations_by_id: dict[int, list[set[int]]] = {}
        for index in index_graph.node_indices():
            subgraph_ids = {index, *ancestors(index_graph, index)}
            sparse_generations_by_id[index] = [gen & subgraph_ids for gen in topological_id_generations]

        return cls(
            type_by_index=type_by_index,
            index_by_type=index_by_type,
            index_graph=index_graph,
            index_sparse_topological_ancestor_generations=sparse_generations_by_id,
        )


_NO_SOLUTION = Solution(infos={}, graph=DependencyGraph.from_dependency_map({}))
SYNC_SOLUTION = ContextVar[Solution[SyncProviderInfo]]("SYNC_SOLUTION", default=_NO_SOLUTION)
FULL_SOLUTION = ContextVar[Solution[ProviderInfo]]("FULL_SOLUTION", default=_NO_SOLUTION)
