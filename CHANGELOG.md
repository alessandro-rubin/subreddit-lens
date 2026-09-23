# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed (dependency and performance review)
- `js_distance_matrix` / `js_similarity` are vectorised with NumPy
  (entropy formulation); same values as SciPy's `jensenshannon` to within
  1e-14, about 20x faster (2,000 users: about 2 s instead of 36 s).
- `scipy.stats` is imported only when posting habits are computed:
  `import subreddit_lens` drops from about 1.2 s to 0.7 s, and every CLI
  command starts faster.
- `generate_graph_figure` draws all edges in one Plotly trace instead of one
  trace per edge (10,000 edges: 0.26 s instead of 2.8 s to build, and far
  faster to render).
- Example notebooks 03, 06, 07, 08 use `get_parent_author()` instead of a
  local re-implementation that still had the comment/submission ID
  collision bug; unused imports removed; undefined `stop` (08) and
  `df_pivot` (05) defined; a duplicated data-loading cell removed from 08.
  Includes the `fix/notebooks-load-comments` branch (notebooks 03, 06, 07,
  08 load data with `load_comments()`).

### Removed (dependency and performance review)
- `embeddings` extra (`sentence-transformers`): used by no notebook or
  module.
- `wordcloud` from the `viz` extra: imported in 05 but never used.
- `extract_zstd(verbose=...)`: unused; `ingest_archive` logs progress per
  chunk.

### Fixed (code review)
- `preprocess` left a stray ')' for Markdown links whose URL contains
  parentheses, e.g. Wikipedia links such as `.../Diritto_(disambigua)`.
- `load_config` raised `TypeError` (shown by the CLI as a traceback) for
  values of the wrong type, e.g. `subreddit = 123`; it now raises
  `ValueError` with the offending key.
- The CLI reports a corrupt or truncated archive in one line instead of a
  traceback.
- `user_metrics` recomputed every neighbour's degree for each user's
  h-index, which is quadratic in the size of the hubs; degrees are now
  computed once (20,000 users: about 2 s instead of about 2 minutes).
- `compute_posting_habits_pdf` looked up every author before checking
  `min_posts`; authors are now filtered by post count first (20x faster
  with many one-post authors).
- `generate_graph_figure` coloured directed graphs by out-degree only; it
  now uses total degree.

### Removed (cleanup)
- `unpack_zst`: superseded by `ingest_archive`, which streams the archive
  instead of decompressing it to disk, and unused elsewhere.
- `subreddit_lens.clustering` (`compute_laplacian`, `spectral_embedding`):
  thin wrappers used only by `08_user_clustering.ipynb`, which now computes
  the same quantities with NumPy and `sklearn.metrics.pairwise.rbf_kernel`
  (verified to give identical results). `order_by_similarity` moved to
  `subreddit_lens.viz`, next to `plot_similarity_matrix`, and is still
  exported from `subreddit_lens`.

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
