"""Comment thread graph construction.

The comment thread graph has comment IDs and submission IDs as nodes, with
edges pointing from parent to child (root-to-leaf direction). It is used for
thread traversal and export via subreddit_lens.export.
"""

import networkx as nx
import pandas as pd

# Values of the 'kind' node attribute set by create_nx_graph().
SUBMISSION = "submission"
COMMENT = "comment"
MISSING = "missing"


def _strip_prefix(ids: pd.Series) -> pd.Series:
    """Remove Reddit type prefixes such as 't1_' or 't3_' from IDs."""
    return ids.str.split("_", n=1).str[-1]


def create_nx_graph(df: pd.DataFrame) -> nx.DiGraph:
    """Build a directed comment thread graph with edges pointing parent to child.

    Each node is a comment ID or a submission ID (the Reddit type prefix such
    as 't1_' or 't3_' is stripped). An edge (parent -> comment) means the
    comment is a direct reply to the parent. This produces a forest of trees,
    one tree per submission thread.

    Every node has a 'kind' attribute:

    - 'submission': a thread root, derived from 'link_id'.
    - 'comment': a comment present in df.
    - 'missing': a parent comment referenced by a reply but absent from df
      (for example outside the collected time window). Missing nodes are
      attached to their submission, so that their replies stay in the right
      thread instead of forming a separate tree.

    Args:
        df: DataFrame with 'id', 'parent_id', and 'link_id' columns.
            'parent_id' and 'link_id' must be in Reddit's 'tX_<id>' format.

    Returns:
        Directed acyclic graph suitable for top-down thread traversal.
        Submission nodes are the only nodes with no incoming edges.

    Note:
        The edge direction here is parent -> child (oldest ancestor to newest
        reply), which is the natural reading order of a conversation. This
        allows straightforward DFS/BFS traversal in subreddit_lens.export.
    """
    comment_ids = df["id"]
    parent_ids = _strip_prefix(df["parent_id"])
    link_ids = _strip_prefix(df["link_id"])

    G = nx.DiGraph()
    G.add_nodes_from(link_ids.drop_duplicates(), kind=SUBMISSION)
    G.add_nodes_from(comment_ids, kind=COMMENT)

    known = set(comment_ids) | set(link_ids)
    for parent, link in zip(parent_ids, link_ids, strict=True):
        if parent not in known:
            G.add_node(parent, kind=MISSING)
            G.add_edge(link, parent)
            known.add(parent)

    G.add_edges_from(zip(parent_ids, comment_ids, strict=True))
    return G
