# subreddit-lens -- subreddit interaction analysis toolkit

Python package (`subreddit_lens`) for exploring and analysing user interactions
in a subreddit, built on Reddit comment archives. It started as an analysis of
r/litigi, an Italian-language subreddit, which is kept as a worked example.

The three main analysis areas are:

1. Posting habits: temporal patterns of user activity (hourly, weekly, monthly).
2. Social network analysis: user interaction graphs, PageRank influence scoring,
   community visualisation.
3. Thread export: extracting Reddit conversation trees as structured data
   (chains and prompt/response pairs, JSONL).

The data source is the Pushshift/Arctic Shift Reddit archive (zstd-compressed
JSON files).

The restructuring plan is in `docs/ROADMAP.md`. Keep its checkboxes up to date
when completing roadmap items.

## Repository Structure

```
src/subreddit_lens/
    __init__.py         Exports the public API.
    cli.py              Typer CLI (`subreddit-lens`): init, ingest, network,
                        metrics, habits, export, run. Thin wrapper around
                        pipeline.py.
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
    clustering/         spectral.py, hierarchical.py (adapted from
                        clustering_utils, formerly a git submodule).
    viz/                graphs.py (network figure), similarity.py (heatmap).
    legacy/             pushshift.py: old scraper, unsupported.
    constants.py        Default excluded authors, removed-comment bodies.
tests/                  pytest suite; conftest.py holds the synthetic
                        fixture dataset (two threads, documented inline).
examples/litigi/        r/litigi notebooks, pipeline steps 01-09.
examples/archive/       Notebooks for other subreddits, not maintained.
docs/                   ROADMAP.md and future documentation.
data/                   Input data files (gitignored -- add files manually).
output/                 Generated figures, exported JSONL, HTML visualisations.
```

Example notebooks (`examples/litigi/`):

```
01_scraping.ipynb          Data collection (legacy Pushshift, non-functional).
02_data_loading.ipynb      zstd to Parquet conversion.
03_eda.ipynb               Exploratory temporal analysis.
04_word_frequency.ipynb    NLTK word frequency (Italian NLP).
05_nlp.ipynb               Sentiment analysis with transformers.
06_posting_habits.ipynb    Per-user posting patterns.
07_network_analysis.ipynb  Interaction graphs, PageRank.
08_user_clustering.ipynb   TF-IDF and spectral clustering.
09_thread_export.ipynb     Conversation chain export.
```

## Setup

This project uses [uv](https://docs.astral.sh/uv/) and requires Python 3.13.

```bash
uv sync                   # core + dev group
uv sync --all-extras      # everything used by the example notebooks
uv run pre-commit install  # once: ruff, mypy, nbstripout on every commit
uv run pytest --cov
uv run ruff check && uv run ruff format --check
uv run mypy
uv run subreddit-lens --help
uv run subreddit-lens run --config examples/litigi/subreddit-lens.toml
uv run jupyter lab
```

## Dependencies and extras

Core dependencies are only what `src/subreddit_lens` imports at module level.
Everything else is an optional extra in `pyproject.toml`:

- `nlp` -- nltk, scikit-learn, stop-words (04, 08)
- `sentiment` -- transformers, torch, datasets, tqdm (05)
- `embeddings` -- sentence-transformers
- `viz` -- matplotlib, seaborn, pyvis, wordcloud (05, 06, 07, 08)
- `som` -- minisom (08)
- `legacy` -- pmaw (01, `subreddit_lens.legacy`)
- `all` -- all of the above except `legacy`

Development tools (pytest, pytest-cov, ruff, mypy with type stubs,
pre-commit, nbstripout, jupyterlab) are in the `dev` dependency group. Keep
`pandas-stubs` and `scipy-stubs` on the same minor version as the installed
library. Add dependencies with `uv add <pkg>`, `uv add --optional <extra> <pkg>`
or `uv add --dev <pkg>`. Never use `!pip install` in notebooks.

## Data

Data files are gitignored and must be added manually. Inputs are
zstandard-compressed newline-delimited JSON dumps named after the subreddit:

    data/litigi_comments.zst       (required)
    data/litigi_submissions.zst    (optional)

`ingest_archive()` streams them to Parquet in chunks, normalised to the
canonical schema in `io/schema.py` (`id` without type prefix, `parent_id` and
`link_id` with it). `examples/litigi/02_data_loading.ipynb` does this for
r/litigi using `examples/litigi/subreddit-lens.toml`. The other notebooks
read:

    data/litigi_comments.parquet
    data/litigi_submissions.parquet

Comment and submission IDs are separate sequences on Reddit and can
coincide: always resolve a parent through its type prefix, never by bare ID.

Notebooks locate the repository root by searching upwards for
`pyproject.toml` and build `DATA_DIR` / `OUTPUT_DIR` from it, so they work
regardless of the Jupyter working directory. Do not use absolute or
platform-specific paths.

## Development Guidelines

- All reusable logic belongs in `src/subreddit_lens/`. Notebooks import from
  `subreddit_lens` rather than defining their own implementations.
- Docstrings follow Google style (Args / Returns / Raises / Example sections).
- All functions must have type annotations.
- Use `pathlib.Path` for all file paths.
- New public functions are exported from their subpackage `__init__.py` and,
  when broadly useful, from `subreddit_lens/__init__.py` (`__all__`).
- Every change to `src/` needs tests in `tests/`.
- Code must pass `ruff check`, `ruff format --check` and `mypy` (strict,
  on `src/` and `tests/`). The `examples/` directory is currently excluded
  from ruff. CI (`.github/workflows/ci.yml`) runs the same checks.
- Coverage must stay at or above 80% (`legacy/` and `viz/` excluded).
- CLI commands contain no analysis logic: they load the Config, apply
  command-line overrides with `dataclasses.replace`, call a `pipeline.run_*`
  function and turn `FileNotFoundError`/`ValueError` into a one-line error
  with exit code 1. New pipeline steps go in `pipeline.py` first.
- networkx graph classes are generic only for type checkers: annotate them
  as `nx.DiGraph[str]` and add `from __future__ import annotations` to the
  module, since `nx.DiGraph[str]` fails at runtime.
- No emojis in code, docstrings, or documentation.
- Notebooks are committed without outputs (they may contain usernames and
  comment text); the nbstripout pre-commit hook and CI enforce this.

## Known Issues

- `01_scraping.ipynb` and `subreddit_lens.legacy` use the Pushshift API, which
  has been heavily restricted since mid-2023. Use Arctic Shift archives and
  `subreddit_lens.io.extract_zstd()` instead.
- Replies to submission authors are only complete when submissions are
  loaded (`get_parent_author(comments, submissions)`). Without them, the
  author of a post is inferred from comments flagged `is_submitter`.
- `07_network_analysis.ipynb` computes PageRank on `G.reverse()`, which ranks
  users who reply to popular users; `user_metrics()` uses `G`, which ranks
  users who receive replies.
- By default `[deleted]` and `AutoModerator` are excluded from per-user
  analyses (`subreddit_lens.constants.DEFAULT_EXCLUDED_AUTHORS`).
- Some example notebooks reference variables defined in removed or reordered
  cells (e.g. `stop` in 08, `df_pivot` in 05); they need a clean re-run.

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

df = load_comments(Path("data/litigi_comments.parquet"))
G = create_nx_graph(df)

chains = extract_thread_chains(G, df, min_length=2)
export_chains_to_jsonl(chains, Path("output/litigi_threads.jsonl"))

pairs = chains_to_prompt_pairs(chains, system_prompt="Sei un utente di r/litigi.")
export_prompt_pairs_to_jsonl(pairs, Path("output/litigi_pairs.jsonl"))
```

See `examples/litigi/09_thread_export.ipynb` for a complete walkthrough.
Check Reddit's current terms before using exported data to train models.
