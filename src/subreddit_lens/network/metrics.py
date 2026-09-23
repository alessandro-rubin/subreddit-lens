"""Node-level metrics for user interaction graphs."""

from collections.abc import Hashable

import networkx as nx


def hindex(G: nx.Graph, node: Hashable) -> int:
    """Compute the h-index of a node within a graph.

    The h-index of node n is the largest integer h such that n has at
    least h neighbours each of which has degree >= h. This is analogous
    to the academic h-index applied to a node's neighbourhood, and gives
    a measure of how influential a user is relative to their connections.

    The metric is computed on the undirected projection of G: for a
    directed graph, the neighbours of n are its predecessors and successors,
    and the degree of a neighbour is its number of distinct neighbours,
    regardless of edge direction. Self-loops are ignored.

    Args:
        G: A NetworkX graph (directed or undirected).
        node: A node identifier present in G.

    Returns:
        Integer h-index value for the node. Returns 0 if the node has no
        neighbours.

    Raises:
        networkx.NetworkXError: If node is not in G.
    """
    U = G.to_undirected(as_view=True) if G.is_directed() else G
    if node not in U:
        raise nx.NetworkXError(f"Node {node!r} is not in the graph")

    def distinct_degree(n: Hashable) -> int:
        return sum(1 for m in U.neighbors(n) if m != n)

    neighbour_degrees = sorted(
        (distinct_degree(m) for m in U.neighbors(node) if m != node),
        reverse=True,
    )
    h = 0
    for i, deg in enumerate(neighbour_degrees, start=1):
        if deg >= i:
            h = i
        else:
            break
    return h
