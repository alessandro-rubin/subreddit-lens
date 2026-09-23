"""NetworkX graph construction for Reddit comment data.

Two distinct graph types are supported:

1. User interaction graph (extract_interaction_graph): nodes are usernames,
   edges represent reply relationships weighted by reply count. Used for
   social network analysis and PageRank scoring.

2. Comment thread graph (create_nx_graph): nodes are comment IDs and
   submission IDs, edges go from parent to child (root-to-leaf direction).
   Used for thread traversal and export via functions.thread_export.
"""

import networkx as nx
import pandas as pd


def get_parent_author(df: pd.DataFrame) -> pd.DataFrame:
    """Add a 'parent_author' column mapping each comment to its parent's author.

    Looks up each comment's parent_id in the same DataFrame. Comments whose
    parent is the submission root (parent_id starts with 't3_') will have
    NaN in 'parent_author' since submissions are not rows in the DataFrame.

    Args:
        df: DataFrame with at least 'id', 'author', and 'parent_id' columns.
            The 'parent_id' column must be in Reddit's 'tX_<id>' format.

    Returns:
        A copy of the input DataFrame with a new 'parent_author' column.
        The original DataFrame is not modified.
    """
    df = df.copy()
    id_to_author = df.set_index("id")["author"].to_dict()
    df["parent_author"] = df["parent_id"].str.split("_").str[1].map(id_to_author)
    return df


def extract_interaction_graph(comment_df: pd.DataFrame) -> nx.DiGraph:
    """Build a weighted directed user interaction graph from a comments DataFrame.

    Each node is a Reddit username. A directed edge (u -> v) with weight w
    means user u replied to user v's comments w times. Self-loops are
    included when a user replies to themselves.

    Args:
        comment_df: DataFrame with at least 'author', 'parent_author', and
            'id' columns. The 'parent_author' column should be pre-computed
            via get_parent_author(). Rows where 'parent_author' is NaN
            (top-level comments replying to a submission) are dropped.

    Returns:
        Directed graph with 'weight' edge attributes representing reply counts.
    """
    user_interactions = (
        comment_df.dropna(subset=["parent_author"])
        .groupby(["author", "parent_author"])
        .agg(count=("id", "count"))
        .reset_index()
    )
    G = nx.DiGraph()
    G.add_edges_from(
        zip(
            user_interactions["author"],
            user_interactions["parent_author"],
            [{"weight": c} for c in user_interactions["count"]],
        )
    )
    return G


def create_nx_graph(df: pd.DataFrame) -> nx.DiGraph:
    """Build a directed comment thread graph with edges pointing parent to child.

    Each node is a comment ID or a submission ID (the Reddit type prefix such
    as 't1_' or 't3_' is stripped). An edge (parent -> comment) means the
    comment is a direct reply to the parent. This produces a forest of trees,
    one tree per submission thread.

    Args:
        df: DataFrame with 'id', 'parent_id', and 'link_id' columns.
            All three columns must be in Reddit's 'tX_<id>' format.

    Returns:
        Directed acyclic graph suitable for top-down thread traversal.
        Submission root nodes (derived from 'link_id') are included as
        nodes with no incoming edges.

    Note:
        The edge direction here is parent -> child (oldest ancestor to newest
        reply), which is the natural reading order of a conversation. This
        allows straightforward DFS/BFS traversal in thread_export functions.
    """
    G = nx.DiGraph()
    G.add_nodes_from(df["id"])
    # Add submission root nodes (strip the 't3_' type prefix)
    G.add_nodes_from(df["link_id"].drop_duplicates().str.split("_").str[1])
    # Edges: parent_id (stripped) -> comment id
    G.add_edges_from(
        zip(
            df["parent_id"].str.split("_").str[1],
            df["id"],
        )
    )
    return G


def symmetrize_graph(G: nx.DiGraph) -> nx.Graph:
    """Convert a directed graph to an undirected graph, merging antiparallel edges.

    For each pair of nodes (u, v) with edges in both directions, the
    undirected edge weight equals the sum of both directed weights. The
    'delta' attribute records the net directional bias
    (weight(u->v) - weight(v->u)). For edges with no reverse direction,
    delta equals the edge weight.

    Args:
        G: Directed graph with optional 'weight' edge attributes.
            Edges without an explicit weight are treated as weight 1.

    Returns:
        Undirected graph with 'weight' and 'delta' edge attributes.
    """
    G_sym = nx.Graph()
    for u, v, data in G.edges(data=True):
        weight = data.get("weight", 1)
        if G.has_edge(v, u):
            reverse_weight = G[v][u].get("weight", 1)
            total_weight = weight + reverse_weight
            delta = weight - reverse_weight
        else:
            total_weight = weight
            delta = weight
        G_sym.add_edge(u, v, weight=total_weight, delta=delta)
    return G_sym


def hindex(G: nx.Graph, node) -> int:
    """Compute the h-index of a node within a graph.

    The h-index of node n is the largest integer h such that n has at
    least h neighbours each of which has degree >= h. This is analogous
    to the academic h-index applied to a node's neighbourhood, and gives
    a measure of how influential a user is relative to their connections.

    Args:
        G: A NetworkX graph (directed or undirected). For directed graphs,
            degree refers to total degree (in + out).
        node: A node identifier present in G.

    Returns:
        Integer h-index value for the node. Returns 0 if the node has no
        neighbours.
    """
    neighbour_degrees = sorted(
        [G.degree(n) for n in G.neighbors(node)], reverse=True
    )
    h = 0
    for i, deg in enumerate(neighbour_degrees, start=1):
        if deg >= i:
            h = i
        else:
            break
    return h
