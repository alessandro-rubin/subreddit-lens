"""User interaction graph construction.

In the user interaction graph, nodes are usernames and edges represent reply
relationships weighted by reply count. It is used for social network analysis
and PageRank scoring.
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
            strict=True,
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
