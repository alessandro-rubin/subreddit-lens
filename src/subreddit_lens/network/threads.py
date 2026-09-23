"""Comment thread graph construction.

The comment thread graph has comment IDs and submission IDs as nodes, with
edges pointing from parent to child (root-to-leaf direction). It is used for
thread traversal and export via subreddit_lens.export.
"""

import networkx as nx
import pandas as pd


def create_nx_graph(df: pd.DataFrame) -> nx.DiGraph:
    """Build a directed comment thread graph with edges pointing parent to child.

    Each node is a comment ID or a submission ID (the Reddit type prefix such
    as 't1_' or 't3_' is stripped). An edge (parent -> comment) means the
    comment is a direct reply to the parent. This produces a forest of trees,
    one tree per submission thread.

    Args:
        df: DataFrame with 'id', 'parent_id', and 'link_id' columns.
            'parent_id' and 'link_id' must be in Reddit's 'tX_<id>' format.

    Returns:
        Directed acyclic graph suitable for top-down thread traversal.
        Submission root nodes (derived from 'link_id') are included as
        nodes with no incoming edges.

    Note:
        The edge direction here is parent -> child (oldest ancestor to newest
        reply), which is the natural reading order of a conversation. This
        allows straightforward DFS/BFS traversal in subreddit_lens.export.
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
            strict=True,
        )
    )
    return G
