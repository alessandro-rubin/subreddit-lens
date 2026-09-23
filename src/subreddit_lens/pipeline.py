"""End-to-end pipeline steps driven by a Config.

Each step reads the inputs named by the configuration, writes its output to
the configured location and returns the path it wrote. The command-line
interface (subreddit_lens.cli) is a thin wrapper around these functions, and
they can be called from notebooks as well.

Steps and their files (for subreddit 'litigi'):

    ingest   data/litigi_comments.zst      -> data/litigi_comments.parquet
             data/litigi_submissions.zst   -> data/litigi_submissions.parquet
    network  comments (+ submissions)      -> output/litigi_users.graphml
    metrics  users graph                   -> output/litigi_user_metrics.csv
    habits   comments                      -> output/litigi_habits.parquet
    export   comments                      -> output/litigi_threads.jsonl
                                              output/litigi_pairs.jsonl
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import networkx as nx
import numpy as np
import pandas as pd

from subreddit_lens.config import Config
from subreddit_lens.export import (
    chains_to_prompt_pairs,
    export_chains_to_jsonl,
    export_prompt_pairs_to_jsonl,
    extract_thread_chains,
)
from subreddit_lens.io import ingest_archive, load_comments, load_submissions
from subreddit_lens.io.ingest import DEFAULT_CHUNK_SIZE as DEFAULT_CHUNK_SIZE
from subreddit_lens.network import (
    create_nx_graph,
    extract_interaction_graph,
    get_parent_author,
    load_graph,
    save_graph,
    user_metrics,
)
from subreddit_lens.temporal import compute_posting_habits_pdf
from subreddit_lens.text import preprocess

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IngestResult:
    """Rows written by run_ingest(); submissions is None when skipped."""

    comments: int
    submissions: int | None


def _require(path: Path, hint: str) -> None:
    if not path.exists():
        raise FileNotFoundError(f"{path} not found. {hint}")


def run_ingest(
    config: Config,
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    extra_columns: Sequence[str] = (),
) -> IngestResult:
    """Convert the configured archives to Parquet.

    The comments archive is required; the submissions archive is ingested
    when present. The configured date range, if any, filters both.

    Args:
        config: Pipeline configuration.
        chunk_size: Records per written chunk (bounds memory use).
        extra_columns: Non-canonical comment fields to keep (e.g.
            'permalink').

    Returns:
        Number of comment and submission rows written.

    Raises:
        FileNotFoundError: If the comments archive does not exist.
    """
    _require(
        config.comments_archive,
        "Download the subreddit's comments dump into the data directory.",
    )
    condition = config.date_filter()
    comments = ingest_archive(
        config.comments_archive,
        config.comments_parquet,
        "comments",
        chunk_size=chunk_size,
        extra_columns=extra_columns,
        condition=condition,
    )
    submissions = None
    if config.submissions_archive.exists():
        submissions = ingest_archive(
            config.submissions_archive,
            config.submissions_parquet,
            "submissions",
            chunk_size=chunk_size,
            condition=condition,
        )
    else:
        logger.warning(
            "%s not found: replies to post authors are inferred from "
            "is_submitter only.",
            config.submissions_archive,
        )
    return IngestResult(comments=comments, submissions=submissions)


def _load_comments(config: Config) -> pd.DataFrame:
    _require(config.comments_parquet, "Run the ingest step first.")
    return load_comments(config.comments_parquet)


def run_network(config: Config) -> Path:
    """Build the user interaction graph and save it as GraphML.

    Submissions are used when their Parquet file exists, so that top-level
    comments count as replies to the author of the post.

    Args:
        config: Pipeline configuration.

    Returns:
        Path of the written graph.

    Raises:
        FileNotFoundError: If the comments Parquet file does not exist.
    """
    comments = _load_comments(config)
    submissions = (
        load_submissions(config.submissions_parquet)
        if config.submissions_parquet.exists()
        else None
    )
    graph = extract_interaction_graph(
        get_parent_author(comments, submissions),
        exclude_authors=config.exclude_authors,
    )
    save_graph(graph, config.users_graph)
    logger.info(
        "User graph: %d users, %d edges -> %s",
        graph.number_of_nodes(),
        graph.number_of_edges(),
        config.users_graph,
    )
    return config.users_graph


def run_metrics(config: Config, *, community_seed: int | None = 0) -> Path:
    """Compute per-user network metrics and write them as CSV.

    Args:
        config: Pipeline configuration.
        community_seed: Seed for Louvain community detection.

    Returns:
        Path of the written CSV file.

    Raises:
        FileNotFoundError: If the user graph does not exist.
        ValueError: If the stored graph is not directed.
    """
    _require(config.users_graph, "Run the network step first.")
    graph = load_graph(config.users_graph)
    if not graph.is_directed():
        raise ValueError(f"{config.users_graph} is not a directed graph")
    metrics = user_metrics(
        cast("nx.DiGraph[str]", graph), community_seed=community_seed
    )
    config.user_metrics_file.parent.mkdir(parents=True, exist_ok=True)
    metrics.to_csv(config.user_metrics_file)
    logger.info("Metrics for %d users -> %s", len(metrics), config.user_metrics_file)
    return config.user_metrics_file


def run_habits(
    config: Config,
    *,
    min_posts: int = 10,
    resolution_minutes: int = 15,
) -> Path:
    """Estimate hourly posting densities per user and write them as Parquet.

    The output has one row per author (index 'author'), an 'n_posts' column,
    and one column per grid point named 'HH:MM' in the configured timezone.

    Args:
        config: Pipeline configuration (timezone, excluded authors).
        min_posts: Minimum number of posts for an author to be included.
        resolution_minutes: Spacing of the evaluation grid; must divide 60.

    Returns:
        Path of the written Parquet file.

    Raises:
        FileNotFoundError: If the comments Parquet file does not exist.
        ValueError: If resolution_minutes does not divide 60.
    """
    if resolution_minutes <= 0 or 60 % resolution_minutes:
        raise ValueError("resolution_minutes must be a positive divisor of 60")
    comments = _load_comments(config)
    steps = 24 * 60 // resolution_minutes
    grid = np.arange(steps) * resolution_minutes / 60
    densities = compute_posting_habits_pdf(
        comments,
        None,
        grid,
        tz=config.timezone,
        min_posts=min_posts,
        exclude_authors=config.exclude_authors,
    )
    labels = [f"{int(h):02d}:{round(h % 1 * 60):02d}" for h in grid]
    table = pd.DataFrame.from_dict(densities, orient="index", columns=labels)
    counts = comments["author"].value_counts()
    table.insert(0, "n_posts", counts.reindex(table.index).astype("int64"))
    table.index.name = "author"
    config.habits_file.parent.mkdir(parents=True, exist_ok=True)
    table.to_parquet(config.habits_file)
    logger.info("Habits for %d users -> %s", len(table), config.habits_file)
    return config.habits_file


def run_export(
    config: Config,
    *,
    min_length: int = 2,
    system_prompt: str = "",
    chains: bool = True,
    pairs: bool = True,
    clean_text: bool = False,
) -> list[Path]:
    """Export conversation chains and/or prompt/response pairs as JSONL.

    Args:
        config: Pipeline configuration.
        min_length: Minimum number of comments per chain.
        system_prompt: System prompt added to every pair.
        chains: Whether to write the chains file.
        pairs: Whether to write the pairs file.
        clean_text: Apply subreddit_lens.text.preprocess() to comment bodies
            (decode HTML entities, drop quoted text and Markdown links,
            collapse whitespace). Pairs whose text becomes empty, e.g.
            replies made only of a quote, are dropped.

    Returns:
        Paths of the written files.

    Raises:
        FileNotFoundError: If the comments Parquet file does not exist.
    """
    comments = _load_comments(config)
    if clean_text:
        comments = comments.assign(body=comments["body"].map(preprocess))
    thread_chains = extract_thread_chains(
        create_nx_graph(comments), comments, min_length=min_length
    )
    config.output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    if chains:
        export_chains_to_jsonl(thread_chains, config.chains_file)
        written.append(config.chains_file)
    if pairs:
        prompt_pairs = chains_to_prompt_pairs(thread_chains, system_prompt)
        if clean_text:
            prompt_pairs = [p for p in prompt_pairs if p["user"] and p["assistant"]]
        export_prompt_pairs_to_jsonl(prompt_pairs, config.pairs_file)
        written.append(config.pairs_file)
    return written
