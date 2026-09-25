# Roadmap: from `reddit_stuff` to `subreddit-lens`

This document is the plan for turning this repository into an installable,
tested Python package and application for exploring user interactions in any
subreddit. The original analysis of a single subreddit, first kept as a worked
example, now lives in a separate project that depends on the package.

Naming conventions used throughout:

| Item                         | Value                                   |
|------------------------------|-----------------------------------------|
| GitHub repository            | `alessandro-rubin/subreddit-lens`       |
| PyPI distribution name       | `subreddit-lens` (free as of 2026-09)   |
| Python import package        | `subreddit_lens`                        |
| CLI command                  | `subreddit-lens`                        |

Each phase ends with a set of acceptance criteria. A phase is done only when
all of them hold. Phases are meant to be delivered as separate pull requests
(or small groups of PRs), in order.

---

## Phase 0 -- Baseline and housekeeping

Goal: freeze the current state and remove sources of confusion before
restructuring.

- [ ] 0.1 Tag the last pre-refactor commit as `v0.0.0-legacy` so that state
      stays reachable (manual step: `git tag v0.0.0-legacy f655fe8` and
      `git push origin v0.0.0-legacy`).
- [x] 0.2 Decide the fate of the `clustering/` submodule:
      - If `clustering_utils` has (or can get) a `pyproject.toml`, depend on it
        with `uv add git+https://github.com/alessandro-rubin/clustering_utils`
        and remove the submodule (`git submodule deinit`, `git rm clustering`,
        delete the `.gitmodules` entry).
      - Otherwise, copy the three functions actually used
        (`ComputeLaplacian`, `SpectralEmbedding`, `order_by_similarity`,
        plus `plot_similarity_matrix`) into the package with attribution.
      - Done: `clustering_utils` has no packaging, so the functions were
        adapted into `subreddit_lens.clustering` and `subreddit_lens.viz`
        and the submodule was removed. Later, `subreddit_lens.clustering`
        was removed too: only `order_by_similarity` (moved to `viz`) was
        used outside notebook 08.
- [x] 0.3 Delete `environment.yml` (conda); `pyproject.toml` + `uv.lock` are
      the single source of truth.
- [x] 0.4 Clean `.gitignore` (remove stale entries such as `lib/`,
      `processed_data`; add `.venv/`, `.ruff_cache/`, `.mypy_cache/`,
      `.pytest_cache/`, `dist/`, `*.egg-info/`).
- [x] 0.5 Add `nbstripout` (as a pre-commit hook in Phase 3) so notebook
      outputs, which may contain usernames and comment text, are never
      committed. Strip existing outputs from `01_scraping.ipynb`,
      `04_word_frequency.ipynb` and `archive/m_tilde.ipynb`.
      (Outputs stripped; the pre-commit hook is part of 3.5.)

Acceptance criteria:
- `git submodule status` is empty, or the submodule decision is documented.
- `uv sync` works from a fresh clone with no extra steps.

---

## Phase 1 -- Installable package

Goal: `uv add git+https://github.com/alessandro-rubin/subreddit-lens` works in
any project, and `import subreddit_lens` works from any directory.

- [x] 1.1 Move to the `src` layout and rename the package:

      ```
      src/subreddit_lens/
          __init__.py
          py.typed
          config.py
          io/            archives.py (zstd), parquet.py, schema.py
          network/       threads.py (comment tree), users.py (interaction graph), metrics.py
          temporal/      habits.py (KDE, JS distance), trends.py
          text/          preprocessing.py, languages/ (it.py, en.py)
          export/        threads.py (chains, prompt pairs, JSONL)
          viz/           graphs.py, similarity.py
          legacy/        pushshift.py (old scraping module)
          cli.py
      tests/
      examples/<subreddit>/
      examples/archive/
      docs/
      ```

      As implemented: `config.py`, `io/schema.py`, `temporal/trends.py` and
      `text/languages/` arrive with Phase 4; a `notebooks/` directory for
      generic tutorials will be added when there is a generic tutorial.

- [x] 1.2 Rewrite `pyproject.toml`:
      - `[build-system]` with the `uv_build` backend (check the current
        version range in the uv docs when doing this).
      - Core `dependencies`: only what the core modules import
        (`pandas`, `pyarrow`, `numpy`, `scipy`, `networkx`, `zstandard`,
        `plotly`, `typer`).
      - `[project.optional-dependencies]`:
        `nlp` (nltk, scikit-learn, stop-words),
        `sentiment` (transformers, torch, datasets, tqdm),
        `embeddings` (sentence-transformers; later removed as unused),
        `viz` (pyvis, matplotlib, seaborn; wordcloud later removed),
        `som` (minisom),
        `legacy` (pmaw),
        `app` (streamlit; dropped with the new Phase 6, replaced by `mcp`),
        `all` (everything above).
      - `[dependency-groups] dev`: pytest, ruff, jupyterlab (pytest-cov,
        mypy, pre-commit and nbstripout are added with Phase 3).
      - `[project.scripts] subreddit-lens = "subreddit_lens.cli:app"`.
      - Metadata: `description`, `license`, `authors`, `keywords`,
        `classifiers`, `[project.urls]`.
      - Remove `jupyter` and `sentence-transformers` from core dependencies.
- [x] 1.3 Optional imports: modules that need an extra raise a clear
      `ImportError` naming the extra to install
      (e.g. `pip install subreddit-lens[mcp]`).
- [x] 1.4 Move the notebooks: generic ones into `notebooks/`, subreddit-specific
      ones into `examples/` (all of them were subreddit-specific). Update all
      imports from `functions` to `subreddit_lens`. (In 0.1.0 the examples
      moved out of the repository altogether.)
- [x] 1.5 Fix the inconsistent notebook paths (three different files, two of
      them misspelt, for the same data, and a fourth name in `CLAUDE.md`).
      Use one configurable data directory and correct file names.
- [x] 1.6 Remove `!pip install` cells from `05_nlp.ipynb` and the Colab paths;
      remove local re-definitions of library functions (e.g. `hindex` in
      `07_network_analysis.ipynb`).
- [x] 1.7 Add `README.md` (what it is, install, quick start, data sources,
      legal notice), `LICENSE` (MIT chosen), `CHANGELOG.md`.
- [x] 1.8 Update `CLAUDE.md` for the new layout.

Acceptance criteria:
- `uv build` produces a wheel and sdist without errors.
- In a clean virtual environment, `pip install dist/*.whl` followed by
  `python -c "import subreddit_lens"` succeeds from outside the repository.
- `subreddit-lens --help` runs.
- No file in the repository imports `functions`.

---

## Phase 2 -- Correctness fixes

Goal: fix the known bugs before building anything on top. Each fix gets a
regression test (the test infrastructure arrives in Phase 3, so do 3.1-3.2
first or together with this phase).

- [x] 2.1 `js_similarity`: `scipy.spatial.distance.jensenshannon` returns the
      JS *distance* (square root of the divergence), bounded by `sqrt(ln 2)`
      with the default base. Use `base=2` so it is bounded in [0, 1], rename to
      `js_distance_matrix` (return distances; let the caller convert to
      similarity), fix the docstring, and compute only the upper triangle.
      (Done as an addition: `js_distance_matrix` is new and `js_similarity`
      is kept as `1 - js_distance_matrix` so existing code keeps working.)
- [x] 2.2 Posting habits timezone: convert `created_utc` to a configurable
      timezone (default `UTC`, e.g. `Europe/Rome` for an Italian subreddit) before
      extracting hours, so DST is handled correctly.
- [x] 2.3 Posting habits performance: replace the per-author boolean filter
      (O(authors x rows)) with a single `groupby("author")`. Add a
      `min_posts` parameter instead of the hard-coded 2.
- [x] 2.4 Posting habits normalisation: the mirrored KDE with `* 3` is an
      approximation; normalise the evaluated density on the grid so it
      integrates to 1 over [0, 24). Make `bw_method` a parameter.
- [x] 2.5 `hindex` on a `DiGraph`: `G.neighbors()` returns successors only, but
      the docstring talks about total degree. Decide on a definition
      (recommended: operate on the undirected projection) and document it.
- [x] 2.6 Author filtering: exclude `[deleted]`, `AutoModerator` and a
      configurable bot list from the user interaction graph and all per-user
      metrics.
- [x] 2.7 `preprocess`: the quote-block regex matches the literal characters
      `\n\n` (backslash-n), not real newlines. Check against real data which
      form the archive uses, fix the pattern, and add tests. Also decode
      all HTML entities with `html.unescape` instead of handling only
      `&amp;` and `&gt;`.
- [x] 2.8 Thread export duplication: `extract_thread_chains` emits one chain
      per root-to-leaf path, so shared prefixes are repeated, and
      `chains_to_prompt_pairs` then emits the same (parent, reply) pair once
      per leaf below it. Generate pairs directly from graph edges
      (each edge = one pair, with optional ancestor context), or deduplicate.
- [x] 2.9 Orphan comments: when a parent comment is missing from the data,
      its ID becomes a fake root in `create_nx_graph`. Mark such roots and
      take `thread_id` from `link_id`, not from the root node.
- [x] 2.10 Replace `print` calls in library code with `logging`; use `tqdm`
      (optional) for progress on long iterations.
- [x] 2.11 Complete type annotations (e.g. `condition: Callable[[dict], bool] | None`
      in the zstd reader, `node: Hashable` in `hindex`, `TypedDict`s for chain
      and pair records).

Acceptance criteria:
- Every item above has at least one test that fails on the old code and
  passes on the new code. (Verified: 24 new tests fail on the Phase 1 code.)
- Results on real data are recomputed and the differences are noted
  in `CHANGELOG.md`. (Pending: needs the real data; the expected direction
  of each change is already listed in `CHANGELOG.md`.)

---

## Phase 3 -- Quality infrastructure

Goal: every change is automatically linted, type-checked and tested.

- [x] 3.1 `tests/conftest.py` (planned as `tests/fixtures/`): a small synthetic dataset (about 2 submissions and
      20 comments, including a deleted comment, an orphan, a self-reply, a
      reply to OP, a bot) with hand-computed expected results.
- [x] 3.2 Unit tests for every public function: `io`, `network`, `temporal`,
      `text`, `export`. Include a round-trip test (zstd -> Parquet -> graph ->
      JSONL) on the fixture.
- [x] 3.3 `ruff` for lint and format (rule sets: `E`, `F`, `I`, `UP`, `B`,
      `SIM`, `D` with Google convention, `NPY`, `PD`), on `src/` and `tests/`.
- [x] 3.3b Lint the example notebooks. Obsolete: after a clean re-run on
      real data, the notebooks moved out of the repository in 0.1.0, and
      ruff no longer excludes anything.
- [x] 3.4 `mypy --strict` on `src/` (or `ty` once it is stable enough).
      Done on `src/` and `tests/`, with pandas, scipy and networkx stubs
      pinned to the installed library versions.
- [x] 3.5 `pre-commit` with ruff, nbstripout, end-of-file/trailing-whitespace
      hooks. Ruff, mypy and nbstripout run as local hooks through `uv run`,
      so they use the versions in `uv.lock`.
- [x] 3.6 GitHub Actions workflow: on push and PR, run
      `uv sync --locked --all-extras`, `ruff check`, `ruff format --check`,
      `mypy`, `pytest --cov`. Matrix on Python 3.13 (add 3.12 if you decide to
      lower `requires-python`). As implemented (`.github/workflows/ci.yml`):
      `uv sync --locked` without extras, since the tests do not need them
      (the dev group includes mcp for the server tests); also builds the
      package. The check that notebooks have no outputs went with the
      notebooks in 0.1.0. Runs on pushes to `master` and on pull requests.
- [x] 3.7 Coverage target: 80% on `src/subreddit_lens` (excluding `viz/`;
      `legacy/` was excluded until its removal in 0.1.0). Enforced by
      `fail_under` in `pyproject.toml`; currently 97% with branch coverage.

Acceptance criteria:
- CI is green on the default branch. (Green on pull request #1; the first
  run on `master` happens once the trigger fix for `master` is merged.)
- `uv run pytest` passes locally in under a minute.

---

## Phase 4 -- Generalised data model

Goal: the package works for any subreddit and handles large archives.

- [x] 4.1 Canonical schema in `io/schema.py` for comments and submissions:
      `id`, `parent_id`, `link_id`, `author`, `created_utc`, `body` / `title`
      + `selftext`, `score`, `subreddit`, `is_submitter`. Normalise type
      prefixes (`t1_`, `t3_`) in one place. Validate on load (plain checks or
      `pandera`). Done with plain checks in `io/schema.py`.
- [x] 4.2 Ingest submissions as well as comments (Arctic Shift provides both).
      With submission authors available, top-level replies get a
      `parent_author` (the OP) and are no longer dropped from the interaction
      graph. Fallback when only comments are available: infer the OP from
      comments with `is_submitter == True` in the same `link_id`.
- [x] 4.3 `Config` object (`config.py`, a dataclass or `pydantic-settings`):
      subreddit, language, timezone, data directory, output directory,
      excluded authors, date range. Loadable from a TOML file. Done with a
      frozen dataclass and `tomllib` (no extra dependency).
- [x] 4.4 Ingestion to Parquet in streaming chunks (write with `pyarrow`
      incrementally) so large dumps never need to fit in memory.
- [ ] 4.5 Evaluate DuckDB (or Polars) for aggregation queries on Parquet
      (per-user counts, edge lists, time series). Keep the pandas API as the
      public interface; use DuckDB internally where it gives a clear speed or
      memory win. Measure on a real dataset before committing to it.
      (Partly done: `Explorer` uses DuckDB over the Parquet files for all
      exploration queries. The pipeline steps still use pandas; moving them
      needs a measurement on the real dataset.)
- [ ] 4.6 Language-aware text processing: `text/languages/it.py` and `en.py`
      with stopwords and stemmer choice; `preprocess(text, lang=...)`.
      (Open: independent of the rest of Phase 4.)
- [x] 4.7 Graph persistence: save and load interaction graphs as GraphML or
      Parquet edge lists so the app does not rebuild them on every run.
      Done with GraphML (`save_graph`, `load_graph`), readable by Gephi.
- [x] 4.8 Network metrics module: PageRank, h-index, degree/strength,
      reciprocity, community detection (`nx.community.louvain_communities`),
      per-user ego-network summaries. One function returns a tidy
      per-user metrics DataFrame. Done: `user_metrics()`.

Acceptance criteria:
- The full pipeline runs on at least two subreddits (in different
  languages) using only a config file. (Pending: needs
  real data; becomes a single command with Phase 5.)
- Peak memory during ingestion stays bounded regardless of archive size.
  (By construction: at most chunk_size records are held in memory; tested
  with chunked writes.)

---

## Phase 5 -- Command-line interface

Goal: the full pipeline is reproducible without notebooks.

- [x] 5.1 Typer app in `cli.py` with commands:

      ```
      subreddit-lens ingest   COMMENTS.zst [SUBMISSIONS.zst] --out data/sub.parquet
      subreddit-lens habits   data/sub.parquet --tz Europe/Rome --out output/habits.parquet
      subreddit-lens network  data/sub.parquet --out output/graph.graphml
      subreddit-lens metrics  output/graph.graphml --out output/users.parquet
      subreddit-lens export   data/sub.parquet --min-length 2 --format pairs --out output/pairs.jsonl
      subreddit-lens app      --config subreddit-lens.toml
      ```

      As implemented: file paths come from the config instead of positional
      arguments (`init`, `ingest`, `network`, `metrics`, `habits`, `export`,
      plus `run` for the whole pipeline). The logic lives in `pipeline.py`
      so notebooks can call the same steps. `app` was dropped with the new
      Phase 6; exploration commands and `mcp` took its place.

- [x] 5.2 Every command accepts `--config FILE` and CLI options override the
      config.
- [x] 5.3 CLI tests with `typer.testing.CliRunner` on the fixture dataset.

Acceptance criteria:
- A new user can go from raw `.zst` files to metrics and JSONL export with
  five commands documented in the README. (Done: `init`, `ingest`,
  `network`, `metrics`, `export`, or `run`; verified end to end on
  synthetic archives.)

---

## Phase 6 -- Exploration and AI access

Goal: answer questions about a subreddit's data without writing pandas code,
from Python, the terminal, SQL or an AI assistant. (Replaces the planned
Streamlit app, which was dropped: a query layer usable by both people and
assistants gives more for less maintenance.)

- [x] 6.1 `Explorer` (`explore.py`): DuckDB views over the Parquet files
      (`comments`, `submissions`, `replies`, `users`, `threads`,
      `user_metrics`, `excluded_authors`) and ready-made analyses: summary,
      top users (including PageRank from the metrics step), user profile,
      activity by hour/weekday/day/month in local time, top threads, thread
      in reading order, text search, strongest interactions.
- [x] 6.2 Read-only SQL: one SELECT per call, row limit, DuckDB sandboxed to
      the data and output directories with its configuration locked.
- [x] 6.3 CLI commands for every analysis (`summary`, `users`, `user`,
      `activity`, `threads`, `thread`, `search`, `interactions`, `sql`,
      `schema`), tables for people and `--json` for scripts and agents.
- [x] 6.4 AI access: `subreddit-lens guide` (views, conventions, example
      SQL) and `subreddit-lens mcp`, an MCP server (`mcp` extra) with one
      read-only tool per analysis plus `run_sql`, sending the guide as its
      instructions. Expected errors reach the assistant with actionable
      messages (e.g. similar usernames).
- [x] 6.5 Tests on the fixture dataset for the views, analyses, SQL
      sandbox, CLI and MCP tools (in-process client).
- [ ] 6.6 Try the MCP server with an assistant on a real dataset and
      refine tool descriptions and defaults from real questions. (Needs the
      real data.)
- [ ] 6.7 Pseudonymisation option: hash usernames (salted, from the config)
      in Explorer results, for demos and for sharing results with hosted
      assistants.
- [ ] 6.8 Network views for assistants: a user's ego network and
      communities as tables (the GraphML is already produced by `network`).

Acceptance criteria:
- After `ingest`, every analysis works from Python, the CLI and MCP on the
  fixture dataset. (Done.)
- An assistant connected through MCP can answer "who are the most
  influential users and what do they talk about?" on a real dataset
  without help. (Pending: 6.6.)

---

## Phase 7 -- Documentation

- [ ] 7.1 MkDocs Material site with `mkdocstrings[python]` for the API
      reference (generated from the Google-style docstrings).
- [ ] 7.2 Pages: installation, data sources (Arctic Shift download steps),
      configuration, CLI reference, exploration and MCP guide, a case study,
      legal and ethical notes.
- [ ] 7.3 Publish to GitHub Pages from a CI workflow.

---

## Phase 8 -- Rename and release

- [ ] 8.1 Rename the GitHub repository to `subreddit-lens`
      (Settings -> General -> Repository name). GitHub redirects the old web
      and git URLs, but the redirect breaks if a new repository named
      `reddit_stuff` is created later. Update local clones with
      `git remote set-url origin https://github.com/alessandro-rubin/subreddit-lens.git`.
      Do this between working sessions, since tools scoped to the old name
      may lose access.
- [ ] 8.2 Update README badges, `[project.urls]` and docs URLs.
- [x] 8.3 Versioning: SemVer; start at `0.1.0`. Keep `CHANGELOG.md` in the
      "Keep a Changelog" format. (0.1.0 is the first release, published by
      hand with `uv publish`; 8.4 automates later releases.)
- [ ] 8.4 Release workflow: on tag `v*`, `uv build` and publish to PyPI with
      trusted publishing (OIDC, no API token stored in secrets). Test on
      TestPyPI first.
- [ ] 8.5 Create the GitHub release with the changelog section.

Acceptance criteria:
- `pip install subreddit-lens` installs the released version from PyPI.

---

## Cross-cutting: legal and ethical constraints

These apply to every phase and must be summarised in the README.

- Reddit usernames are pseudonymous personal data; for users in the EU the
  GDPR applies. Do not redistribute raw dumps; offer
  hashed usernames in anything published (screenshots, datasets, demos).
- Reddit's User Agreement and Data API Terms restrict using Reddit content to
  train machine-learning models without an agreement with Reddit. Obtaining
  the data through Pushshift or Arctic Shift archives does not change this.
  Check the current terms before using or distributing the output of the
  thread export beyond personal research, and state this in the docs of the
  `export` module.
- The `legacy/pushshift.py` scraper (the Pushshift API has been restricted
  since mid-2023) was removed in 0.1.0 with the `legacy` extra; data comes
  from the Arctic Shift archives.

---

## Suggested order of pull requests

1. Phase 0 (housekeeping)
2. Phase 1 (package layout, pyproject, README) + Phase 3.1-3.3 (fixtures,
   first tests, ruff)
3. Phase 2 (bug fixes, each with a regression test)
4. Phase 3.4-3.7 (mypy, pre-commit, CI, coverage)
5. Phase 4 (data model, submissions, config)
6. Phase 5 (CLI)
7. Phase 6 (exploration and AI access)
8. Phase 7 (docs)
9. Phase 8 (rename, first PyPI release)
