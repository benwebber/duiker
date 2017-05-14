import collections
import copy
import enum
from collections.abc import (
    Sequence,
    Set,
)

__all__ = ['DAG', 'tsort']


Mark = enum.Enum('Mark', ['TEMPORARY', 'PERMANENT'])


class DAG(collections.defaultdict):

    def __init__(self, graph=None):
        super().__init__(set)
        if graph is None:
            return
        try:
            for vertex, successors in graph.items():
                if not isinstance(successors, (Sequence, Set)):
                    raise ValueError('successors must be sequence or set, not {.__name__}'.format(type(successors)))
                for successor in successors:
                    self.add(vertex, successor)
        except AttributeError:
            raise ValueError('graph data must be a mapping, not {.__name__}'.format(type(graph)))

    @property
    def edges(self):
        for vertex, successors in self.items():
            for successor in successors:
                yield (vertex, successor)

    @property
    def vertices(self):
        return self.keys()

    def add(self, vertex, successor):
        self[vertex].add(successor)
        # Call __getitem__ for its factory side-effect. This normalizes the
        # graph by creating empty sets for sinks. Otherwise they will be created
        # while sorting, which leads to different sort orders on first run and
        # subsequent runs.
        self[successor]


def tsort(graph):
    sorted_nodes, unmarked_nodes, marks = collections.deque(), set(graph), {}

    def visit(node):
        mark = marks.get(node)
        if mark == Mark.TEMPORARY:
            raise ValueError('cycle detected')
        if not mark:
            marks[node] = Mark.TEMPORARY
            for child in graph[node]:
                visit(child)
            marks[node] = Mark.PERMANENT
            sorted_nodes.appendleft(node)

    while unmarked_nodes:
        visit(unmarked_nodes.pop())

    return sorted_nodes
