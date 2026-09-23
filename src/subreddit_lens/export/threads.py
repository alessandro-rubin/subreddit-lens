"""Thread tree traversal and export for Reddit conversation data.

Reddit comments form a forest of trees: each submission is a root node,
and each comment is a child of either the submission or another comment.
This module traverses those trees and exports conversation chains as
structured data for language model fine-tuning.

The graph passed to these functions must have edges pointing from parent
to child (as produced by network.create_nx_graph()). Each root-to-leaf
path in a tree represents one conversation chain in natural reading order.

Typical usage:

    from pathlib import Path
    from functions.io import load_comments
    from functions.network import create_nx_graph, get_parent_author
    from functions.thread_export import extract_thread_chains, export_chains_to_jsonl

    df = load_comments(Path("data/litigi_comments.parquet"))
    G = create_nx_graph(df)

    chains = extract_thread_chains(G, df, min_length=2)
    export_chains_to_jsonl(chains, Path("output/litigi_threads.jsonl"))
"""

import json
from pathlib import Path

import networkx as nx
import pandas as pd

# Comment bodies set by Reddit when a user deletes or moderators remove a comment.
_REMOVED_BODIES = {"[deleted]", "[removed]"}


def extract_thread_chains(
    G: nx.DiGraph,
    df: pd.DataFrame,
    min_length: int = 2,
) -> list[dict]:
    """Extract all root-to-leaf conversation chains from a comment thread graph.

    Traverses the DAG produced by network.create_nx_graph() using an
    iterative depth-first search (avoids Python recursion limits on large
    comment corpora). Each chain is a root-to-leaf path annotated with
    comment metadata from the DataFrame.

    Args:
        G: Directed comment graph with edges pointing from parent to child,
            as produced by network.create_nx_graph(). Submission root nodes
            have in-degree 0.
        df: DataFrame with at least 'id', 'author', and 'body' columns.
            Used to annotate each node in the chain with text and author.
        min_length: Minimum number of comments a chain must contain to be
            included. Chains shorter than this are excluded. Default is 2
            (at least one prompt-response pair).

    Returns:
        List of chain dicts, each with keys:
            'thread_id' (str): The submission root node ID.
            'chain' (list of dict): Ordered list of comment metadata dicts,
                each containing 'comment_id', 'author', and 'body'.
                The chain runs from the oldest ancestor to the newest reply.
    """
    # Build a fast lookup from comment ID to author + body.
    id_to_row = df.set_index("id")[["author", "body"]].to_dict(orient="index")

    # Root nodes are submission IDs: they have no incoming edges.
    root_nodes = [n for n in G.nodes() if G.in_degree(n) == 0]

    chains: list[dict] = []

    for root in root_nodes:
        # Iterative DFS with an explicit stack to avoid hitting Python's
        # recursion limit (default 1000) on deeply nested comment trees.
        # Stack holds (current_node, path_so_far).
        stack: list[tuple] = [(root, [])]

        while stack:
            node, path = stack.pop()
            # Extend the current path with comment metadata if this node
            # is a comment (submissions are roots and have no body in df).
            if node in id_to_row:
                path = path + [
                    {
                        "comment_id": node,
                        "author": id_to_row[node]["author"],
                        "body": id_to_row[node]["body"],
                    }
                ]

            children = list(G.successors(node))
            if children:
                # Push children onto the stack for continued traversal.
                for child in children:
                    stack.append((child, path))
            else:
                # Leaf node: the current path is a complete chain.
                if len(path) >= min_length:
                    chains.append({"thread_id": root, "chain": path})

    return chains


def export_chains_to_jsonl(
    chains: list[dict],
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
    output_path = Path(output_path)
    with open(output_path, "w", encoding="utf-8") as f:
        for chain in chains:
            f.write(json.dumps(chain, ensure_ascii=False) + "\n")
    print(f"Wrote {len(chains)} chains to {output_path}")
    return len(chains)


def chains_to_prompt_pairs(
    chains: list[dict],
    system_prompt: str = "",
    skip_removed: bool = True,
) -> list[dict]:
    """Convert conversation chains into prompt/response pairs for fine-tuning.

    Each consecutive comment pair within a chain produces one training
    sample. This is the simplest format for supervised fine-tuning (SFT)
    and is compatible with most training frameworks.

    Args:
        chains: List of chain dicts as returned by extract_thread_chains().
        system_prompt: A system-level instruction prepended to every training
            sample. Leave empty for no system prompt.
        skip_removed: If True (default), adjacent pairs that contain a
            deleted or removed comment body ('[deleted]' or '[removed]') are
            excluded from the output.

    Returns:
        List of training sample dicts, each with keys:
            'system' (str): The system prompt (may be empty).
            'user' (str): The prompt comment body.
            'assistant' (str): The response comment body.

    Example:
        >>> pairs = chains_to_prompt_pairs(chains, system_prompt="Sei un utente di r/litigi.")
        >>> pairs[0]
        {'system': 'Sei un utente di r/litigi.', 'user': '...', 'assistant': '...'}
    """
    pairs: list[dict] = []

    for chain_obj in chains:
        comments = chain_obj["chain"]
        for i in range(len(comments) - 1):
            user_body = comments[i]["body"]
            assistant_body = comments[i + 1]["body"]

            if skip_removed and (
                user_body in _REMOVED_BODIES or assistant_body in _REMOVED_BODIES
            ):
                continue

            pairs.append(
                {
                    "system": system_prompt,
                    "user": user_body,
                    "assistant": assistant_body,
                }
            )

    return pairs


def export_prompt_pairs_to_jsonl(
    pairs: list[dict],
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
    output_path = Path(output_path)
    with open(output_path, "w", encoding="utf-8") as f:
        for pair in pairs:
            f.write(json.dumps(pair, ensure_ascii=False) + "\n")
    print(f"Wrote {len(pairs)} prompt/response pairs to {output_path}")
    return len(pairs)
