"""Explore and analyse user interactions in a subreddit.

subreddit_lens provides reusable functions for three analysis areas:

1. Posting habits -- hourly activity KDEs and similarity matrices.
2. Social network analysis -- user interaction graphs and influence metrics.
3. Thread export -- conversation chain extraction for language model training.

Subpackages:
    config      Per-subreddit settings loaded from a TOML file.
    io          zstd archives, chunked ingestion to Parquet, canonical schema.
    text        Text cleaning for Reddit comments.
    network     Thread graphs, user interaction graphs, metrics, storage.
    temporal    KDE-based posting activity analysis, JS similarity.
    export      Thread tree traversal and JSONL export for training data.
    clustering  Spectral and hierarchical clustering utilities.
    viz         Plotly figures for graphs and similarity matrices.
    legacy      Pushshift scraper (unsupported, non-functional since 2023).

Quick start:

    from pathlib import Path

    from subreddit_lens import create_nx_graph, extract_thread_chains, load_comments

    df = load_comments(Path("data/litigi_comments.parquet"))
    G = create_nx_graph(df)
    chains = extract_thread_chains(G, df, min_length=2)
"""

from importlib.metadata import PackageNotFoundError, version

from subreddit_lens.clustering import (
    compute_laplacian,
    order_by_similarity,
    spectral_embedding,
)
from subreddit_lens.config import Config, load_config
from subreddit_lens.export import (
    chains_to_prompt_pairs,
    export_chains_to_jsonl,
    export_prompt_pairs_to_jsonl,
    extract_thread_chains,
)
from subreddit_lens.io import (
    extract_zstd,
    ingest_archive,
    load_comments,
    load_submissions,
    unpack_zst,
)
from subreddit_lens.network import (
    create_nx_graph,
    extract_interaction_graph,
    get_parent_author,
    hindex,
    load_graph,
    save_graph,
    symmetrize_graph,
    user_metrics,
)
from subreddit_lens.temporal import (
    compute_posting_habits_pdf,
    js_distance_matrix,
    js_similarity,
    local_hour,
)
from subreddit_lens.text import preprocess
from subreddit_lens.viz import generate_graph_figure, plot_similarity_matrix

try:
    __version__ = version("subreddit-lens")
except PackageNotFoundError:  # pragma: no cover - package not installed
    __version__ = "0.0.0"

__all__ = [
    "__version__",
    # config
    "Config",
    "load_config",
    # io
    "extract_zstd",
    "ingest_archive",
    "load_comments",
    "load_submissions",
    "unpack_zst",
    # text
    "preprocess",
    # network
    "create_nx_graph",
    "extract_interaction_graph",
    "get_parent_author",
    "hindex",
    "load_graph",
    "save_graph",
    "symmetrize_graph",
    "user_metrics",
    # temporal
    "compute_posting_habits_pdf",
    "js_distance_matrix",
    "js_similarity",
    "local_hour",
    # export
    "chains_to_prompt_pairs",
    "export_chains_to_jsonl",
    "export_prompt_pairs_to_jsonl",
    "extract_thread_chains",
    # clustering
    "compute_laplacian",
    "order_by_similarity",
    "spectral_embedding",
    # viz
    "generate_graph_figure",
    "plot_similarity_matrix",
]
