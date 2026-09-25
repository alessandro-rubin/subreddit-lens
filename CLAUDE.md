# subreddit-lens -- subreddit interaction analysis toolkit

Python package (`subreddit_lens`) for exploring and analysing user interactions
in a subreddit, built on Reddit comment archives. Published on PyPI as
`subreddit-lens`.

The three main analysis areas are:

1. Posting habits: temporal patterns of user activity (hourly, weekly, monthly).
2. Social network analysis: user interaction graphs, PageRank influence scoring,
   community visualisation.
3. Thread export: extracting Reddit conversation trees as structured data
   (chains and prompt/response pairs, JSONL).

On top of them, `explore.py` (`Explorer`) answers common questions over the
ingested data with DuckDB, exposed through CLI commands and an MCP server so
AI assistants can query a subreddit with little setup.

The data source is the Pushshift/Arctic Shift Reddit archive (zstd-compressed
JSON files).

The restructuring plan is in `docs/ROADMAP.md`. Keep its checkboxes up to date
when completing roadmap items.

## Repository Structure

```
src/subreddit_lens/
    __init__.py         Exports the public API.
    cli.py              Typer CLI (`subreddit-lens`). Pipeline: init,
                        ingest, network, metrics, habits, export, run
                        (wrappers around pipeline.py). Explore: summary,
                        users, user, activity, threads, thread, search,
                        interactions, sql, schema (wrappers around
                        Explorer). AI: guide, mcp.
    explore.py          Explorer: DuckDB views over the Parquet files
                        (comments, submissions, replies, users, threads,
                        user_metrics, excluded_authors), ready-made
                        analyses, sandboxed read-only sql(); to_jsonable.
    guide.py            GUIDE text: printed by `guide`, sent as the MCP
                        server instructions.
    mcp_server.py       build_server(explorer): read-only MCP tools (needs
                        the `mcp` extra; imported lazily by the CLI).
    pipeline.py         run_ingest/run_network/run_metrics/run_habits/
                        run_export: one step each, driven by a Config.
    config.py           Config dataclass and load_config() (TOML).
    io/                 archives.py (zstd readers), schema.py (canonical
                        columns, normalize), ingest.py (chunked zstd to
                        Parquet), parquet.py (load_comments/submissions).
    text/               preprocessing.py: comment text cleaning.
    network/            threads.py (comment tree graph), users.py (user
                        interaction graph), metrics.py (h-index,
                        user_metrics), storage.py (GraphML save/load).
    temporal/           habits.py: KDE hourly activity, JS similarity.
    export/             threads.py: thread chains, prompt pairs, JSONL export.
    viz/                graphs.py (network figure), similarity.py (heatmap,
                        order_by_similarity).
    constants.py        Default excluded authors, removed-comment bodies.
tests/                  pytest suite; conftest.py holds the synthetic
                        fixture dataset (two threads, documented inline).
docs/                   ROADMAP.md and future documentation.
data/                   Input data files (gitignored -- add files manually).
output/                 Generated figures, exported JSONL, HTML visualisations.
```

## Setup

This project uses [uv](https://docs.astral.sh/uv/) and requires Python 3.13.

```bash
uv sync                   # core + dev group
uv sync --all-extras      # also the mcp extra
uv run pre-commit install  # once: ruff and mypy on every commit
uv run pytest --cov
uv run ruff check && uv run ruff format --check
uv run mypy
uv run subreddit-lens --help
uv run subreddit-lens run --config path/to/subreddit-lens.toml
uv run subreddit-lens summary --config path/to/subreddit-lens.toml
uv build                  # wheel and sdist in dist/
```

## Dependencies and extras

Core dependencies are only what `src/subreddit_lens` imports at module level
(including DuckDB, used by `explore.py`). Optional extras in `pyproject.toml`
cover the modules that need more:

- `mcp` -- mcp, the Model Context Protocol SDK (`subreddit-lens mcp`)

Libraries used only by an analysis built on top of the package (plotting,
NLP, sentiment models) belong in that analysis project, not here.

Development tools (pytest, pytest-cov, ruff, mypy with type stubs,
pre-commit, and mcp for the server tests) are in the `dev` dependency group.
Keep `pandas-stubs` and `scipy-stubs` on the same minor version as the
installed library. Add dependencies with `uv add <pkg>`,
`uv add --optional <extra> <pkg>` or `uv add --dev <pkg>`.

## Data

Data files are gitignored and must be added manually. Inputs are
zstandard-compressed newline-delimited JSON dumps named after the subreddit,
in `archive_dir` (default: `data_dir`):

    <subreddit>_comments.zst       (required)
    <subreddit>_submissions.zst    (optional)

`ingest_archive()` streams them to Parquet in chunks, normalised to the
canonical schema in `io/schema.py` (`id` without type prefix, `parent_id` and
`link_id` with it), and the pipeline writes the results to `data_dir`:

    <subreddit>_comments.parquet
    <subreddit>_submissions.parquet

Comment and submission IDs are separate sequences on Reddit and can
coincide: always resolve a parent through its type prefix, never by bare ID.

## Development Guidelines

- All reusable logic belongs in `src/subreddit_lens/`.
- The repository holds no analyses of specific subreddits: examples in
  docstrings, docs and tests use neutral names (`askhistorians`, `demo`).
  Analyses of a particular subreddit live in separate projects that depend on
  the published package.
- Docstrings follow Google style (Args / Returns / Raises / Example sections).
- All functions must have type annotations.
- Use `pathlib.Path` for all file paths.
- New public functions are exported from their subpackage `__init__.py` and,
  when broadly useful, from `subreddit_lens/__init__.py` (`__all__`).
- Every change to `src/` needs tests in `tests/`.
- Code must pass `ruff check`, `ruff format --check` and `mypy` (strict,
  on `src/` and `tests/`). CI (`.github/workflows/ci.yml`) runs the same
  checks and builds the package.
- Coverage must stay at or above 80% (`viz/` excluded).
- CLI commands contain no analysis logic: they load the Config, apply
  command-line overrides with `dataclasses.replace`, call a `pipeline.run_*`
  function or an `Explorer` method and turn `FileNotFoundError`/`ValueError`
  into a one-line error with exit code 1. New pipeline steps go in
  `pipeline.py` first, new analyses in `explore.py`.
- Explorer rules: `sql()` accepts exactly one SELECT statement and the
  DuckDB connection is sandboxed (only data_dir and output_dir are readable,
  configuration locked); keep it that way. Ready-made analyses return
  DataFrames (or dicts of them) with comment text HTML-decoded and truncated
  to `max_chars`. Invalid input raises `QueryError` (a `ValueError`); for
  unknown usernames it lists similar names.
- MCP tools are read-only, return `to_jsonable(...)` results, cap sizes, and
  wrap their body in `_expected_errors()` so `ValueError` and
  `FileNotFoundError` reach the assistant as a `ToolError` message (the SDK
  hides the text of other exceptions). When adding a view or analysis, also
  update `guide.py`, the CLI and the MCP tools.
- networkx graph classes are generic only for type checkers: annotate them
  as `nx.DiGraph[str]` and add `from __future__ import annotations` to the
  module, since `nx.DiGraph[str]` fails at runtime.
- No emojis in code, docstrings, or documentation.
- Releases: bump `version` in `pyproject.toml`, move the `[Unreleased]`
  section of `CHANGELOG.md` under the new version, `uv build`, then
  `uv publish` (needs a PyPI token). A version number cannot be reused on
  PyPI.

## Known Issues

- Replies to submission authors are only complete when submissions are
  loaded (`get_parent_author(comments, submissions)`). Without them, the
  author of a post is inferred from comments flagged `is_submitter`.
- `user_metrics()` computes PageRank on the reply graph `G` (edges from the
  replier to the replied-to), which ranks users who receive replies;
  PageRank on `G.reverse()` would rank users who reply to popular users.
- By default `[deleted]` and `AutoModerator` are excluded from per-user
  analyses (`subreddit_lens.constants.DEFAULT_EXCLUDED_AUTHORS`).

## Thread Export

```python
from pathlib import Path

from subreddit_lens import create_nx_graph, load_comments
from subreddit_lens.export import (
    chains_to_prompt_pairs,
    export_chains_to_jsonl,
    export_prompt_pairs_to_jsonl,
    extract_thread_chains,
)

df = load_comments(Path("data/askhistorians_comments.parquet"))
G = create_nx_graph(df)

chains = extract_thread_chains(G, df, min_length=2)
export_chains_to_jsonl(chains, Path("output/askhistorians_threads.jsonl"))

pairs = chains_to_prompt_pairs(chains, system_prompt="You post on r/askhistorians.")
export_prompt_pairs_to_jsonl(pairs, Path("output/askhistorians_pairs.jsonl"))
```

Check Reddit's current terms before using exported data to train models.
