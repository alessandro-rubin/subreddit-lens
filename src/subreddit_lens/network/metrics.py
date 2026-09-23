"""Node-level metrics for user interaction graphs."""

from collections.abc import Hashable

import networkx as nx


def hindex(G: nx.Graph, node: Hashable) -> int:
    """Compute the h-index of a node within a graph.

    The h-index of node n is the largest integer h such that n has at
    least h neighbours each of which has degree >= h. This is analogous
    to the academic h-index applied to a node's neighbourhood, and gives
    a measure of how influential a user is relative to their connections.

    Args:
        G: A NetworkX graph (directed or undirected). For directed graphs,
            neighbours are the successors of node, and degree refers to
            total degree (in + out).
        node: A node identifier present in G.

    Returns:
        Integer h-index value for the node. Returns 0 if the node has no
        neighbours.
    """
    neighbour_degrees = sorted((G.degree(n) for n in G.neighbors(node)), reverse=True)
    h = 0
    for i, deg in enumerate(neighbour_degrees, start=1):
        if deg >= i:
            h = i
        else:
            break
    return h
