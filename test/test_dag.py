import collections
import copy

import pytest

from duiker import dag

#     5  7  3
#     | /| /|
#  +-11  8  |
#  |  |\ |  |
#  |  2  9 10
#  +-------/
DATA = {
    5: {11},
    7: {11, 8},
    3: {8, 10},
    11: {2, 9, 10},
    8: {9}
}
GRAPH = dag.DAG({2: set(), 3: {8, 10}, 5: {11}, 7: {11, 8}, 8: {9}, 9: set(), 10: set(), 11: {2, 9, 10}})


@pytest.fixture
def acyclic_graph():
    data = copy.copy(DATA)
    return dag.DAG(data)

@pytest.fixture
def cyclic_graph():
    data = copy.copy(DATA)
    # introduce cycle between 5-11
    data.update({11: {2, 5, 9, 10}})
    return dag.DAG(data)


class TestDAG:
    @pytest.mark.parametrize('data,expected', [
        (DATA, GRAPH),
        (None, dag.DAG()),
    ])
    def test_good_input(self, data, expected):
        assert dag.DAG(data) == expected

    @pytest.mark.parametrize('data', ['string', {5: 1}])
    def test_bad_input(self, data):
        with pytest.raises(ValueError):
            dag.DAG(data)

    def test_edges(self, acyclic_graph):
        assert sorted(list(acyclic_graph.edges)) == [(3, 8), (3, 10), (5, 11), (7, 8), (7, 11), (8, 9), (11, 2), (11, 9), (11, 10)]

    def test_vertices(self, acyclic_graph):
        assert sorted(list(acyclic_graph.vertices)) == [2, 3, 5, 7, 8, 9, 10, 11]

def test_tsort(acyclic_graph, cyclic_graph):
    assert dag.tsort(acyclic_graph) == collections.deque([7, 5, 11, 3, 10, 8, 9, 2])
    with pytest.raises(ValueError):
        dag.tsort(cyclic_graph)
