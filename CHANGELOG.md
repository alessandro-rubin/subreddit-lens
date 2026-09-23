# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added (Phase 5)
- Command-line interface: `subreddit-lens init | ingest | network | metrics
  | habits | export | run`, driven by the TOML config, with overrides such
  as `--data-dir`, `--output-dir`, `--start/--end`, `--timezone`. Errors are
  reported in one line with exit code 1.
- `subreddit_lens.pipeline`: `run_ingest`, `run_network`, `run_metrics`,
  `run_habits`, `run_export`, callable from Python.
- Output paths on `Config` (`users_graph`, `user_metrics_file`,
  `habits_file`, `chains_file`, `pairs_file`).
- `export --preprocess` / `run_export(clean_text=True)`: clean comment text
  before exporting (raw Reddit bodies contain HTML entities such as `&gt;`).

### Added (Phase 4)
- `ingest_archive()`: streams a zstd archive to Parquet in chunks with a
  fixed schema, writing to a temporary file that is renamed on success.
- Canonical schema for comments and submissions (`io/schema.py`):
  `normalize()`, `SchemaError`, `strip_type_prefix()`. `load_comments()`
  now validates and normalises its input; `load_submissions()` is new.
- `get_parent_author(comments, submissions)`: top-level comments are
  attributed to the author of the post, from submissions or, without them,
  from comments flagged `is_submitter`. **The interaction graph gains the
  replies to post authors.**
- `Config` and `load_config()` for per-subreddit TOML settings (paths,
  timezone, language, date range, excluded authors);
  `examples/litigi/subreddit-lens.toml`.
- `save_graph()` / `load_graph()` (GraphML).
- `user_metrics()`: per-user replies sent/received, reciprocity, ego size,
  PageRank, h-index and Louvain community in one DataFrame.

### Fixed (Phase 4)
- `get_parent_author` looked up submission parents ('t3_x') among comment
  IDs, so a top-level reply could be credited to the author of an unrelated
  comment with the same ID.

### Fixed
- `js_similarity` used `jensenshannon` with the natural log, so similarity
  never went below `1 - sqrt(ln 2) ~ 0.17`. It now uses base 2 and is
  bounded in [0, 1]. **Similarity values change**: re-run clustering results.
- Posting-habit hours were computed in UTC. `compute_posting_habits_pdf` now
  takes a `tz` argument (the litigi notebooks use `Europe/Rome`) and uses
  fractional hours instead of whole hours.
- Posting-habit densities are normalised to integrate to 1 on the grid
  instead of being multiplied by 3.
- `hindex` on a directed graph only counted successors; it now uses the
  undirected projection and ignores self-loops. **Values change** for users
  who mostly receive replies.
- `preprocess` did not remove quote blocks (the pattern matched a literal
  backslash-n), and only decoded `&amp;` and `&gt;`. It now decodes all HTML
  entities, removes quote blocks with real or escaped newlines, and removes
  Markdown escapes.
- `chains_to_prompt_pairs` emitted the same (comment, reply) pair once per
  chain containing it; each pair is now emitted once. **The number of
  exported pairs drops** for branching threads.
- A reply whose parent comment is missing from the data became a separate
  tree with the missing ID as `thread_id`. Missing parents are now
  placeholder nodes (`kind="missing"`) attached to their submission.
- `extract_thread_chains` crashed when an ID appeared twice (e.g. an edited
  comment collected twice); the last row now wins.
- `extract_zstd` crashed on blank lines in an archive.

### Added
- `js_distance_matrix`, `local_hour`, and the `min_posts`, `bw_method`,
  `tz` and `exclude_authors` parameters of `compute_posting_habits_pdf`.
- `exclude_authors` parameter of `extract_interaction_graph`. By default
  `[deleted]` and `AutoModerator` are excluded from the interaction graph
  and from posting habits.
- `kind` node attribute (`submission`, `comment`, `missing`) in the graph
  returned by `create_nx_graph`.
- `Chain`, `ChainComment` and `PromptPair` TypedDicts in
  `subreddit_lens.export`.
- Strict mypy, extended ruff rules (pydocstyle, NumPy, pandas), coverage
  threshold (80%), pre-commit hooks (ruff, mypy, nbstripout) and a GitHub
  Actions CI workflow.
- Test suite with a synthetic fixture dataset (`tests/conftest.py`) covering
  every subpackage, including a zstd -> Parquet -> JSONL round trip.
- Installable package `subreddit_lens` (src layout, `uv_build` backend).
- Optional dependency extras: `nlp`, `sentiment`, `embeddings`, `viz`, `som`,
  `legacy`, `all`.
- `subreddit-lens` command-line entry point (currently `version` only).
- `subreddit_lens.clustering` (`compute_laplacian`, `spectral_embedding`,
  `order_by_similarity`) and `subreddit_lens.viz.plot_similarity_matrix`,
  adapted from the `clustering_utils` repository.
- README, LICENSE (MIT), roadmap, smoke tests, ruff configuration.

### Changed
- Dependencies upgraded to current releases: pandas 3.0, numpy 2.5,
  scipy 1.18, networkx 3.7, plotly 7.1, pyarrow 25. Type stubs follow
  (pandas-stubs 3.0, scipy-stubs 1.18). No code changes were needed; the
  test suite passes with deprecation warnings treated as errors.
- CI runs on pushes to `master` (the default branch), not `main`.
- Package renamed from `functions` to `subreddit_lens` and split into
  subpackages (`io`, `text`, `network`, `temporal`, `export`, `clustering`,
  `viz`, `legacy`).
- Notebooks moved to `examples/litigi/` and `examples/archive/`; they now
  read and write `data/litigi_comments.parquet` under the repository root.
- `jupyter` and `sentence-transformers` are no longer core dependencies.
- `ComputeLaplacian` / `SpectralEmbedding` renamed to `compute_laplacian` /
  `spectral_embedding`.
- Library code logs through `logging` instead of printing.
- The litigi notebooks 03, 06 and 08 use `Europe/Rome` local time.

### Removed
- `clustering/` git submodule.
- `environment.yml` (conda); `pyproject.toml` and `uv.lock` are the single
  source of truth.
- `!pip install` cells and Colab paths from `05_nlp.ipynb`.
