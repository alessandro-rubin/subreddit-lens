"""User interaction graph construction.

In the user interaction graph, nodes are usernames and edges represent reply
relationships weighted by reply count. It is used for social network analysis
and PageRank scoring.

Comment and submission IDs are separate sequences on Reddit, so the same ID
can belong to a comment and to a submission; parents are always resolved by
their type prefix ('t1_' comment, 't3_' submission).
"""

from __future__ import annotations

from collections.abc import Iterable

import networkx as nx
import pandas as pd

from subreddit_lens.constants import DEFAULT_EXCLUDED_AUTHORS
from subreddit_lens.io.schema import strip_type_prefix


def _submitter_by_thread(df: pd.DataFrame) -> pd.Series:
    """Infer each thread's submitter from comments flagged 'is_submitter'."""
    flagged = df[df["is_submitter"].astype("boolean").fillna(False).astype(bool)]
    threads = strip_type_prefix(flagged["link_id"])
    return flagged["author"].groupby(threads.to_numpy()).first()


def get_parent_author(
    df: pd.DataFrame,
    submissions: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Add a 'parent_author' column mapping each comment to its parent's author.

    Replies to comments (parent_id 't1_...') are resolved against the
    comments in df. Top-level comments (parent_id 't3_...') reply to the
    submission, so their parent author is the submitter (OP), taken from:

    1. submissions, when given (the reliable source);
    2. otherwise, comments in the same thread with 'is_submitter' set, when
       df has that column (the OP is known only if they commented);
    3. otherwise NaN.

    Parents missing from the data also get NaN.

    Args:
        df: DataFrame with at least 'id', 'author', and 'parent_id' columns.
            'parent_id' must be in Reddit's 'tX_<id>' format. 'link_id' and
            'is_submitter' are used for the fallback when present.
        submissions: Optional DataFrame of submissions with 'id' and
            'author' columns (e.g. from subreddit_lens.io.load_submissions).

    Returns:
        A copy of the input DataFrame with a new 'parent_author' column.
        The original DataFrame is not modified.
    """
    df = df.copy()
    parent_ids = df["parent_id"].astype("string")
    parent_keys = strip_type_prefix(parent_ids)
    replies_to_comment = parent_ids.str.startswith("t1_").fillna(False)
    replies_to_submission = parent_ids.str.startswith("t3_").fillna(False)

    comment_authors = df.drop_duplicates("id", keep="last").set_index("id")["author"]
    parent_author = pd.Series(pd.NA, index=df.index, dtype="object")
    parent_author[replies_to_comment] = parent_keys[replies_to_comment].map(
        comment_authors
    )

    if submissions is not None:
        op = submissions.drop_duplicates("id", keep="last")
        op_authors = op.set_index(strip_type_prefix(op["id"]))["author"]
    elif "is_submitter" in df.columns and "link_id" in df.columns:
        op_authors = _submitter_by_thread(df)
    else:
        op_authors = None
    if op_authors is not None:
        parent_author[replies_to_submission] = parent_keys[replies_to_submission].map(
            op_authors
        )

    df["parent_author"] = parent_author
    return df


def extract_interaction_graph(
    comment_df: pd.DataFrame,
    exclude_authors: Iterable[str] | None = DEFAULT_EXCLUDED_AUTHORS,
) -> nx.DiGraph[str]:
    """Build a weighted directed user interaction graph from a comments DataFrame.

    Each node is a Reddit username. A directed edge (u -> v) with weight w
    means user u replied to user v's comments w times. Self-loops are
    included when a user replies to themselves.

    Args:
        comment_df: DataFrame with at least 'author', 'parent_author', and
            'id' columns. The 'parent_author' column should be pre-computed
            via get_parent_author(). Rows where 'parent_author' is NaN
            (parent missing from the data, or top-level comment whose
            submitter is unknown) are dropped.
        exclude_authors: Usernames removed from the graph, both as repliers
            and as reply targets. Defaults to '[deleted]' and
            'AutoModerator'. Pass None to keep every author.

    Returns:
        Directed graph with 'weight' edge attributes representing reply counts.
    """
    interactions = comment_df.dropna(subset=["parent_author"])
    if exclude_authors is not None:
        excluded = list(exclude_authors)
        interactions = interactions[
            ~interactions["author"].isin(excluded)
            & ~interactions["parent_author"].isin(excluded)
        ]
    user_interactions = (
        interactions.groupby(["author", "parent_author"])
        .agg(count=("id", "count"))
        .reset_index()
    )
    G: nx.DiGraph[str] = nx.DiGraph()
    G.add_edges_from(
        zip(
            user_interactions["author"],
            user_interactions["parent_author"],
            [{"weight": c} for c in user_interactions["count"]],
            strict=True,
        )
    )
    return G


def symmetrize_graph(G: nx.DiGraph[str]) -> nx.Graph[str]:
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
    G_sym: nx.Graph[str] = nx.Graph()
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
