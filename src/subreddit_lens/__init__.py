"""Explore and analyse user interactions in a subreddit.

subreddit_lens provides reusable functions for three analysis areas:

1. Posting habits -- hourly activity KDEs and similarity matrices.
2. Social network analysis -- user interaction graphs and influence metrics.
3. Thread export -- conversation chain extraction for language model training.

On top of them, Explorer answers common questions (top users, profiles,
activity, threads, search, SQL) over the ingested data, and the same
analyses are available from the CLI and an MCP server for AI assistants.

Modules and subpackages:
    config      Per-subreddit settings loaded from a TOML file.
    explore     Explorer: DuckDB views and ready-made analyses.
    guide       Usage guide shared by the CLI and the MCP server.
    mcp_server  MCP server exposing Explorer (needs the 'mcp' extra).
    io          zstd archives, chunked ingestion to Parquet, canonical schema.
    text        Text cleaning for Reddit comments.
    network     Thread graphs, user interaction graphs, metrics, storage.
    temporal    KDE-based posting activity analysis, JS similarity.
    export      Thread tree traversal and JSONL export for training data.
    viz         Plotly figures for graphs and similarity matrices.
    legacy      Pushshift scraper (unsupported, non-functional since 2023).

Quick start:

    from pathlib import Path

    from subreddit_lens import Explorer

    with Explorer.from_config(Path("subreddit-lens.toml")) as ex:
        print(ex.summary())
        print(ex.top_users("replies_received", n=10))
        print(ex.sql("SELECT count(*) FROM comments"))
"""

from importlib.metadata import PackageNotFoundError, version

from subreddit_lens.config import Config, load_config
from subreddit_lens.explore import Explorer, QueryError, to_json, to_jsonable
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
from subreddit_lens.viz import (
    generate_graph_figure,
    order_by_similarity,
    plot_similarity_matrix,
)

try:
    __version__ = version("subreddit-lens")
except PackageNotFoundError:  # pragma: no cover - package not installed
    __version__ = "0.0.0"

__all__ = [
    "__version__",
    # config
    "Config",
    "load_config",
    # explore
    "Explorer",
    "QueryError",
    "to_json",
    "to_jsonable",
    # io
    "extract_zstd",
    "ingest_archive",
    "load_comments",
    "load_submissions",
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
    # viz
    "generate_graph_figure",
    "order_by_similarity",
    "plot_similarity_matrix",
]
