"""Reddit analysis toolkit for r/litigi.

This package provides reusable functions for the three main analysis areas:

1. Posting habits analysis -- hourly activity KDEs and similarity matrices.
2. Social network analysis -- user interaction graphs and influence metrics.
3. Thread export -- conversation chain extraction for bot training data.

Submodules:
    preprocessing   Text cleaning for Italian Reddit comments.
    io              Data loading from zstd archives and Parquet files.
    network         NetworkX graph construction and network metrics.
    posting_habits  KDE-based posting activity analysis, JS similarity.
    thread_export   Thread tree traversal and JSONL export for training data.
    visualization   Plotly interactive figure generation for graphs.
    scraping        Legacy Pushshift scraper (largely non-functional post-2023).

Quick start:

    from functions import (
        load_comments,
        preprocess,
        get_parent_author,
        extract_interaction_graph,
        create_nx_graph,
        symmetrize_graph,
        hindex,
        compute_posting_habits_pdf,
        js_similarity,
        extract_thread_chains,
        export_chains_to_jsonl,
        chains_to_prompt_pairs,
        generate_graph_figure,
    )
"""

from functions.io import extract_zstd, load_comments, unpack_zst
from functions.network import (
    create_nx_graph,
    extract_interaction_graph,
    get_parent_author,
    hindex,
    symmetrize_graph,
)
from functions.posting_habits import compute_posting_habits_pdf, js_similarity
from functions.preprocessing import preprocess
from functions.thread_export import (
    chains_to_prompt_pairs,
    export_chains_to_jsonl,
    export_prompt_pairs_to_jsonl,
    extract_thread_chains,
)
from functions.visualization import generate_graph_figure

__all__ = [
    # io
    "extract_zstd",
    "unpack_zst",
    "load_comments",
    # preprocessing
    "preprocess",
    # network
    "get_parent_author",
    "extract_interaction_graph",
    "create_nx_graph",
    "symmetrize_graph",
    "hindex",
    # posting_habits
    "compute_posting_habits_pdf",
    "js_similarity",
    # thread_export
    "extract_thread_chains",
    "export_chains_to_jsonl",
    "chains_to_prompt_pairs",
    "export_prompt_pairs_to_jsonl",
    # visualization
    "generate_graph_figure",
]
