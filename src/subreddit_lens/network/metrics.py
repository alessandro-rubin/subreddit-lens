"""Node-level metrics for user interaction graphs."""

from __future__ import annotations

import math
from collections.abc import Hashable, Iterable

import networkx as nx
import pandas as pd

from subreddit_lens.network.users import symmetrize_graph


def _h_index(values: Iterable[int]) -> int:
    """Largest h such that at least h of the values are >= h."""
    h = 0
    for i, value in enumerate(sorted(values, reverse=True), start=1):
        if value < i:
            break
        h = i
    return h


def hindex[N: Hashable](G: nx.Graph[N], node: N) -> int:
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
    U: nx.Graph[N] = G.to_undirected(as_view=True) if G.is_directed() else G
    if node not in U:
        raise nx.NetworkXError(f"Node {node!r} is not in the graph")

    def distinct_degree(n: N) -> int:
        return sum(1 for m in U.neighbors(n) if m != n)

    return _h_index(distinct_degree(m) for m in U.neighbors(node) if m != node)


def user_metrics(
    G: nx.DiGraph[str],
    *,
    weight: str = "weight",
    community_seed: int | None = 0,
) -> pd.DataFrame:
    """Compute per-user network metrics from a user interaction graph.

    The graph is expected to follow extract_interaction_graph(): an edge
    u -> v with weight w means u replied w times to v. Self-loops (users
    replying to themselves) are ignored.

    Columns:

    - replies_sent / replies_received: weighted out- and in-degree.
    - users_replied_to / repliers: unweighted out- and in-degree.
    - ego_size: number of distinct users interacted with, either way.
    - reciprocity: share of those users with replies in both directions
      (NaN for users with no interactions).
    - pagerank: weighted PageRank on G. Because edges point from the replier
      to the user replied to, a user ranks high when they receive replies,
      especially from users who themselves receive many replies.
    - hindex: see hindex().
    - community: Louvain community on the symmetrised graph, numbered by
      decreasing size (0 is the largest); -1 for users whose only
      interactions are with themselves.

    Args:
        G: Directed user interaction graph.
        weight: Edge attribute holding reply counts.
        community_seed: Random seed for Louvain, for reproducible
            communities. None for a random run.

    Returns:
        DataFrame indexed by username, sorted by decreasing PageRank.
    """
    H: nx.DiGraph[str] = nx.DiGraph(G)
    H.remove_edges_from(list(nx.selfloop_edges(H)))
    nodes = list(H.nodes)
    if not nodes:
        return pd.DataFrame(
            columns=[
                "replies_sent",
                "replies_received",
                "users_replied_to",
                "repliers",
                "ego_size",
                "reciprocity",
                "pagerank",
                "hindex",
                "community",
            ]
        ).rename_axis("author")

    pagerank = nx.pagerank(H, weight=weight)
    communities = sorted(
        nx.community.louvain_communities(
            symmetrize_graph(H), weight=weight, seed=community_seed
        ),
        key=lambda c: (-len(c), min(c)),
    )
    community_of = {n: i for i, members in enumerate(communities) for n in members}

    # Degrees on the undirected projection, computed once: calling hindex()
    # per user would recompute every neighbour's degree, which is quadratic
    # in the size of the hubs. H has no self-loops, so degree counts
    # distinct neighbours.
    undirected = H.to_undirected(as_view=True)
    degree = dict(undirected.degree())

    rows = []
    for n in nodes:
        successors = set(H.successors(n))
        predecessors = set(H.predecessors(n))
        neighbours = successors | predecessors
        rows.append(
            {
                "author": n,
                "replies_sent": H.out_degree(n, weight=weight),
                "replies_received": H.in_degree(n, weight=weight),
                "users_replied_to": len(successors),
                "repliers": len(predecessors),
                "ego_size": len(neighbours),
                "reciprocity": (
                    len(successors & predecessors) / len(neighbours)
                    if neighbours
                    else math.nan
                ),
                "pagerank": pagerank[n],
                "hindex": _h_index(degree[m] for m in undirected.neighbors(n)),
                "community": community_of.get(n, -1),
            }
        )
    return (
        pd.DataFrame(rows).set_index("author").sort_values("pagerank", ascending=False)
    )
