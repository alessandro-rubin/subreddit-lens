# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Installable package `subreddit_lens` (src layout, `uv_build` backend).
- Optional dependency extras: `nlp`, `sentiment`, `embeddings`, `viz`, `som`,
  `legacy`, `all`.
- `subreddit-lens` command-line entry point (currently `version` only).
- `subreddit_lens.clustering` (`compute_laplacian`, `spectral_embedding`,
  `order_by_similarity`) and `subreddit_lens.viz.plot_similarity_matrix`,
  adapted from the `clustering_utils` repository.
- README, LICENSE (MIT), roadmap, smoke tests, ruff configuration.

### Changed
- Package renamed from `functions` to `subreddit_lens` and split into
  subpackages (`io`, `text`, `network`, `temporal`, `export`, `clustering`,
  `viz`, `legacy`).
- Notebooks moved to `examples/litigi/` and `examples/archive/`; they now
  read and write `data/litigi_comments.parquet` under the repository root.
- `jupyter` and `sentence-transformers` are no longer core dependencies.
- `ComputeLaplacian` / `SpectralEmbedding` renamed to `compute_laplacian` /
  `spectral_embedding`.

### Removed
- `clustering/` git submodule.
- `environment.yml` (conda); `pyproject.toml` and `uv.lock` are the single
  source of truth.
- `!pip install` cells and Colab paths from `05_nlp.ipynb`.
