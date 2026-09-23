"""Thread tree traversal and export for Reddit conversation data.

Reddit comments form a forest of trees: each submission is a root node,
and each comment is a child of either the submission or another comment.
This module traverses those trees and exports conversation chains as
structured data for language model fine-tuning.

The graph passed to these functions must have edges pointing from parent
to child (as produced by subreddit_lens.network.create_nx_graph()). Each
root-to-leaf path in a tree represents one conversation chain in natural
reading order.

Typical usage:

    from pathlib import Path
    from subreddit_lens.io import load_comments
    from subreddit_lens.network import create_nx_graph
    from subreddit_lens.export import extract_thread_chains, export_chains_to_jsonl

    df = load_comments(Path("data/litigi_comments.parquet"))
    G = create_nx_graph(df)

    chains = extract_thread_chains(G, df, min_length=2)
    export_chains_to_jsonl(chains, Path("output/litigi_threads.jsonl"))
"""

import json
import logging
from collections.abc import Hashable, Iterable
from pathlib import Path
from typing import Any, TypedDict

import networkx as nx
import pandas as pd

from subreddit_lens.constants import REMOVED_BODIES
from subreddit_lens.network.threads import SUBMISSION

logger = logging.getLogger(__name__)


class ChainComment(TypedDict):
    """One comment inside a conversation chain."""

    comment_id: str
    author: str
    body: str


class Chain(TypedDict):
    """A root-to-leaf conversation path inside one submission thread."""

    thread_id: str
    chain: list[ChainComment]


class PromptPair(TypedDict):
    """A (comment, reply) training sample in system/user/assistant format."""

    system: str
    user: str
    assistant: str


def _root_nodes(G: nx.DiGraph) -> list[Hashable]:
    """Return submission nodes, or in-degree-0 nodes for unlabelled graphs."""
    kinds = nx.get_node_attributes(G, "kind")
    if kinds:
        return [n for n, kind in kinds.items() if kind == SUBMISSION]
    return [n for n in G.nodes() if G.in_degree(n) == 0]


def extract_thread_chains(
    G: nx.DiGraph,
    df: pd.DataFrame,
    min_length: int = 2,
) -> list[Chain]:
    """Extract all root-to-leaf conversation chains from a comment thread graph.

    Traverses the DAG produced by subreddit_lens.network.create_nx_graph()
    using an iterative depth-first search (avoids Python recursion limits on
    large comment corpora). Each chain is a root-to-leaf path annotated with
    comment metadata from the DataFrame.

    Chains that share a prefix repeat the shared comments: a comment with
    three replies appears in (at least) three chains. Use
    chains_to_prompt_pairs() to obtain each (comment, reply) pair once.

    Args:
        G: Directed comment graph with edges pointing from parent to child,
            as produced by subreddit_lens.network.create_nx_graph(). Roots
            are the nodes whose 'kind' attribute is 'submission'; for graphs
            without 'kind' attributes, nodes with in-degree 0 are used.
        df: DataFrame with at least 'id', 'author', and 'body' columns.
            Used to annotate each node in the chain with text and author.
            If an ID appears more than once (e.g. an edited comment
            collected twice), the last row wins.
        min_length: Minimum number of comments a chain must contain to be
            included. Chains shorter than this are excluded. Default is 2
            (at least one prompt-response pair).

    Returns:
        List of chain dicts, each with keys:
            'thread_id' (str): The submission ID of the thread.
            'chain' (list of dict): Ordered list of comment metadata dicts,
                each containing 'comment_id', 'author', and 'body'.
                The chain runs from the oldest ancestor to the newest reply.
                Nodes missing from df (placeholders for absent parents) are
                skipped.
    """
    id_to_row = (
        df.drop_duplicates(subset="id", keep="last")
        .set_index("id")[["author", "body"]]
        .to_dict(orient="index")
    )

    chains: list[Chain] = []

    for root in _root_nodes(G):
        # Iterative DFS with an explicit stack to avoid hitting Python's
        # recursion limit (default 1000) on deeply nested comment trees.
        # Stack holds (current_node, path_so_far).
        stack: list[tuple[Hashable, list[ChainComment]]] = [(root, [])]

        while stack:
            node, path = stack.pop()
            # Extend the current path with comment metadata if this node is a
            # comment in df (submissions and missing parents have no row).
            if node in id_to_row:
                row = id_to_row[node]
                path = [
                    *path,
                    ChainComment(
                        comment_id=str(node), author=row["author"], body=row["body"]
                    ),
                ]

            children = list(G.successors(node))
            if children:
                stack.extend((child, path) for child in children)
            elif len(path) >= min_length:
                # Leaf node: the current path is a complete chain.
                chains.append(Chain(thread_id=str(root), chain=path))

    return chains


def _write_jsonl(records: Iterable[Any], output_path: str | Path) -> int:
    """Write records to a JSONL file and return the number of lines written."""
    count = 0
    with Path(output_path).open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            count += 1
    return count


def export_chains_to_jsonl(
    chains: list[Chain],
    output_path: str | Path,
) -> int:
    """Write conversation chains to a JSONL file (one JSON object per line).

    Each line contains a complete chain with its thread_id and the ordered
    list of comments. The file can be used directly for inspection or
    further processed into training pairs via chains_to_prompt_pairs().

    Args:
        chains: List of chain dicts as returned by extract_thread_chains().
        output_path: Destination file path. The parent directory must exist.
            Existing files are overwritten. The '.jsonl' extension is
            conventional but not enforced.

    Returns:
        Number of JSON lines written to the file.

    Raises:
        OSError: If the output path is not writable or the parent directory
            does not exist.
    """
    count = _write_jsonl(chains, output_path)
    logger.info("Wrote %d chains to %s", count, output_path)
    return count


def chains_to_prompt_pairs(
    chains: list[Chain],
    system_prompt: str = "",
    skip_removed: bool = True,
) -> list[PromptPair]:
    """Convert conversation chains into prompt/response pairs for fine-tuning.

    Each (comment, direct reply) pair produces one training sample. Because
    chains that share a prefix repeat the shared comments, the same pair can
    occur in several chains; it is emitted only once, the first time it is
    seen. This is the simplest format for supervised fine-tuning (SFT) and is
    compatible with most training frameworks.

    Args:
        chains: List of chain dicts as returned by extract_thread_chains().
        system_prompt: A system-level instruction prepended to every training
            sample. Leave empty for no system prompt.
        skip_removed: If True (default), pairs that contain a deleted or
            removed comment body ('[deleted]' or '[removed]') are excluded
            from the output.

    Returns:
        List of training sample dicts, each with keys:
            'system' (str): The system prompt (may be empty).
            'user' (str): The prompt comment body.
            'assistant' (str): The response comment body.

    Example:
        >>> pairs = chains_to_prompt_pairs(
        ...     chains, system_prompt="Sei un utente di r/litigi."
        ... )
        >>> pairs[0]
        {'system': 'Sei un utente di r/litigi.', 'user': '...', 'assistant': '...'}
    """
    pairs: list[PromptPair] = []
    # A reply has exactly one parent, so its comment ID identifies the pair.
    seen_replies: set[str] = set()

    for chain_obj in chains:
        comments = chain_obj["chain"]
        for parent, reply in zip(comments, comments[1:], strict=False):
            if reply["comment_id"] in seen_replies:
                continue
            seen_replies.add(reply["comment_id"])

            if skip_removed and (
                parent["body"] in REMOVED_BODIES or reply["body"] in REMOVED_BODIES
            ):
                continue

            pairs.append(
                PromptPair(
                    system=system_prompt,
                    user=parent["body"],
                    assistant=reply["body"],
                )
            )

    return pairs


def export_prompt_pairs_to_jsonl(
    pairs: list[PromptPair],
    output_path: str | Path,
) -> int:
    """Write prompt/response pairs to a JSONL file for fine-tuning.

    Args:
        pairs: List of training sample dicts as returned by
            chains_to_prompt_pairs().
        output_path: Destination file path. Existing files are overwritten.

    Returns:
        Number of JSON lines written to the file.

    Raises:
        OSError: If the output path is not writable.
    """
    count = _write_jsonl(pairs, output_path)
    logger.info("Wrote %d prompt/response pairs to %s", count, output_path)
    return count
