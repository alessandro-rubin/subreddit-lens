# Roadmap: from `reddit_stuff` to `subreddit-lens`

This document is the plan for turning this repository into an installable,
tested Python package and application for exploring user interactions in any
subreddit. The r/litigi analysis becomes the first worked example rather than
the whole project.

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

- [ ] 0.1 Tag the current `main` as `v0.0.0-legacy` so the pre-refactor state
      stays reachable (manual step: `git tag v0.0.0-legacy <main sha>` and
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
        and the submodule was removed.
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
          clustering/    spectral.py, hierarchical.py
          viz/           graphs.py, similarity.py
          legacy/        pushshift.py (old scraping module)
          cli.py
      tests/
      examples/litigi/
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
        `embeddings` (sentence-transformers),
        `viz` (pyvis, matplotlib, seaborn, wordcloud),
        `som` (minisom),
        `legacy` (pmaw),
        `app` (streamlit, added with Phase 6),
        `all` (everything above).
      - `[dependency-groups] dev`: pytest, ruff, jupyterlab (pytest-cov,
        mypy, pre-commit and nbstripout are added with Phase 3).
      - `[project.scripts] subreddit-lens = "subreddit_lens.cli:app"`.
      - Metadata: `description`, `license`, `authors`, `keywords`,
        `classifiers`, `[project.urls]`.
      - Remove `jupyter` and `sentence-transformers` from core dependencies.
- [x] 1.3 Optional imports: modules that need an extra raise a clear
      `ImportError` naming the extra to install
      (e.g. `pip install subreddit-lens[viz]`).
- [x] 1.4 Move the notebooks: generic ones into `notebooks/`, r/litigi-specific
      ones into `examples/litigi/` (all current notebooks are r/litigi-specific,
      so they all went to `examples/litigi/`). Update all imports from `functions` to
      `subreddit_lens`.
- [x] 1.5 Fix the inconsistent notebook paths. Notebooks currently read from
      `processed_data/itigi_comments_2024.parqet`,
      `processed_data/itigi_comments_copnsolidated.parqet`,
      `data/litigi.pickle`, while `CLAUDE.md` says `data/litigi_comments.parquet`.
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
      timezone (default `UTC`, `Europe/Rome` for the litigi example) before
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
- Results on the litigi example are recomputed and the differences are noted
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
- [ ] 3.3 `ruff` for lint and format (rule sets: `E`, `F`, `I`, `UP`, `B`,
      `SIM`, `D` with Google convention, `NPY`, `PD`). Partly done: `E`,
      `F`, `I`, `UP`, `B`, `SIM` are enabled on `src/` and `tests/`.
- [ ] 3.3b Lint the example notebooks (remove `examples` from ruff's
      `extend-exclude`). They currently have unused imports and undefined
      names left from Colab-era cell reordering (`stop` in 08, `df_pivot`
      in 05); fix them with a clean top-to-bottom re-run on real data.
- [ ] 3.4 `mypy --strict` on `src/` (or `ty` once it is stable enough).
- [ ] 3.5 `pre-commit` with ruff, nbstripout, end-of-file/trailing-whitespace
      hooks.
- [ ] 3.6 GitHub Actions workflow: on push and PR, run
      `uv sync --locked --all-extras`, `ruff check`, `ruff format --check`,
      `mypy`, `pytest --cov`. Matrix on Python 3.13 (add 3.12 if you decide to
      lower `requires-python`).
- [ ] 3.7 Coverage target: 80% on `src/subreddit_lens` (excluding `legacy/`
      and `viz/`).

Acceptance criteria:
- CI is green on the default branch.
- `uv run pytest` passes locally in under a minute.

---

## Phase 4 -- Generalised data model

Goal: the package works for any subreddit and handles large archives.

- [ ] 4.1 Canonical schema in `io/schema.py` for comments and submissions:
      `id`, `parent_id`, `link_id`, `author`, `created_utc`, `body` / `title`
      + `selftext`, `score`, `subreddit`, `is_submitter`. Normalise type
      prefixes (`t1_`, `t3_`) in one place. Validate on load (plain checks or
      `pandera`).
- [ ] 4.2 Ingest submissions as well as comments (Arctic Shift provides both).
      With submission authors available, top-level replies get a
      `parent_author` (the OP) and are no longer dropped from the interaction
      graph. Fallback when only comments are available: infer the OP from
      comments with `is_submitter == True` in the same `link_id`.
- [ ] 4.3 `Config` object (`config.py`, a dataclass or `pydantic-settings`):
      subreddit, language, timezone, data directory, output directory,
      excluded authors, date range. Loadable from a TOML file.
- [ ] 4.4 Ingestion to Parquet in streaming chunks (write with `pyarrow`
      incrementally) so large dumps never need to fit in memory.
- [ ] 4.5 Evaluate DuckDB (or Polars) for aggregation queries on Parquet
      (per-user counts, edge lists, time series). Keep the pandas API as the
      public interface; use DuckDB internally where it gives a clear speed or
      memory win. Measure on the litigi dataset before committing to it.
- [ ] 4.6 Language-aware text processing: `text/languages/it.py` and `en.py`
      with stopwords and stemmer choice; `preprocess(text, lang=...)`.
- [ ] 4.7 Graph persistence: save and load interaction graphs as GraphML or
      Parquet edge lists so the app does not rebuild them on every run.
- [ ] 4.8 Network metrics module: PageRank, h-index, degree/strength,
      reciprocity, community detection (`nx.community.louvain_communities`),
      per-user ego-network summaries. One function returns a tidy
      per-user metrics DataFrame.

Acceptance criteria:
- The full pipeline runs on at least two subreddits (r/litigi plus one
  English-language subreddit) using only a config file.
- Peak memory during ingestion stays bounded regardless of archive size.

---

## Phase 5 -- Command-line interface

Goal: the full pipeline is reproducible without notebooks.

- [ ] 5.1 Typer app in `cli.py` with commands:

      ```
      subreddit-lens ingest   COMMENTS.zst [SUBMISSIONS.zst] --out data/sub.parquet
      subreddit-lens habits   data/sub.parquet --tz Europe/Rome --out output/habits.parquet
      subreddit-lens network  data/sub.parquet --out output/graph.graphml
      subreddit-lens metrics  output/graph.graphml --out output/users.parquet
      subreddit-lens export   data/sub.parquet --min-length 2 --format pairs --out output/pairs.jsonl
      subreddit-lens app      --config subreddit-lens.toml
      ```

- [ ] 5.2 Every command accepts `--config FILE` and CLI options override the
      config.
- [ ] 5.3 CLI tests with `typer.testing.CliRunner` on the fixture dataset.

Acceptance criteria:
- A new user can go from raw `.zst` files to metrics and JSONL export with
  five commands documented in the README.

---

## Phase 6 -- Interactive application

Goal: explore user interactions in a browser.

- [ ] 6.1 Streamlit app in `src/subreddit_lens/app/` (installed with the `app`
      extra, launched by `subreddit-lens app`). Pages:
      - Overview: volume over time, active users, top threads.
      - User explorer: search a user, see activity profile (hour/weekday
        heatmap), top interlocutors, ego network, metrics.
      - Network: interaction graph filtered by date range and minimum edge
        weight, coloured by community, sized by PageRank.
      - Thread browser: pick a submission, view the comment tree.
      - Similarity: users clustered by posting-habit similarity.
- [ ] 6.2 The app reads precomputed artifacts from Phase 5 (Parquet, GraphML)
      and caches them with `st.cache_data` / `st.cache_resource`.
- [ ] 6.3 Large graphs: render only the top-N nodes by PageRank or the
      selected user's neighbourhood; plain Plotly/pyvis rendering does not
      scale beyond a few thousand nodes.
- [ ] 6.4 Pseudonymisation toggle: display hashed usernames (salted hash from
      the config) for demos and screenshots.
- [ ] 6.5 Smoke test with `streamlit.testing.v1.AppTest`.

Acceptance criteria:
- `subreddit-lens app` starts and all pages render on the fixture dataset
  and on the litigi dataset.

---

## Phase 7 -- Documentation

- [ ] 7.1 MkDocs Material site with `mkdocstrings[python]` for the API
      reference (generated from the Google-style docstrings).
- [ ] 7.2 Pages: installation, data sources (Arctic Shift download steps),
      configuration, CLI reference, app guide, the r/litigi case study,
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
- [ ] 8.3 Versioning: SemVer; start at `0.1.0`. Keep `CHANGELOG.md` in the
      "Keep a Changelog" format.
- [ ] 8.4 Release workflow: on tag `v*`, `uv build` and publish to PyPI with
      trusted publishing (OIDC, no API token stored in secrets). Test on
      TestPyPI first.
- [ ] 8.5 Create the GitHub release with the changelog section.

Acceptance criteria:
- `pip install subreddit-lens` installs the released version from PyPI.

---

## Cross-cutting: legal and ethical constraints

These apply to every phase and must be summarised in the README.

- Reddit usernames are pseudonymous personal data; users of r/litigi are
  mostly in the EU, so GDPR applies. Do not redistribute raw dumps; offer
  hashed usernames in anything published (screenshots, datasets, demos).
- Reddit's User Agreement and Data API Terms restrict using Reddit content to
  train machine-learning models without an agreement with Reddit. Obtaining
  the data through Pushshift or Arctic Shift archives does not change this.
  Check the current terms before using or distributing the output of the
  thread export beyond personal research, and state this in the docs of the
  `export` module.
- The `legacy/pushshift.py` scraper is kept for reference only and should be
  documented as unsupported.

---

## Suggested order of pull requests

1. Phase 0 (housekeeping)
2. Phase 1 (package layout, pyproject, README) + Phase 3.1-3.3 (fixtures,
   first tests, ruff)
3. Phase 2 (bug fixes, each with a regression test)
4. Phase 3.4-3.7 (mypy, pre-commit, CI, coverage)
5. Phase 4 (data model, submissions, config)
6. Phase 5 (CLI)
7. Phase 6 (app)
8. Phase 7 (docs)
9. Phase 8 (rename, first PyPI release)
