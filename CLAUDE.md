# reddit_stuff -- r/litigi Analysis Toolkit

Analysis of r/litigi, an Italian-language subreddit. The three main goals are:

1. Posting habits: temporal patterns of user activity (hourly, weekly, monthly).
2. Social network analysis: user interaction graphs, PageRank influence scoring,
   community visualisation.
3. Thread export: extracting Reddit conversation trees as structured training data
   (prompt/response pairs) for language model fine-tuning.

The data source is the Pushshift/Arctic Shift Reddit archive (zstd-compressed JSON files).

## Repository Structure

```
functions/
    __init__.py         Exports the full public API.
    preprocessing.py    Text cleaning for Italian Reddit comments.
    io.py               Data loading from zstd archives and Parquet files.
    network.py          NetworkX graph construction and network metrics.
    posting_habits.py   KDE-based hourly activity analysis, JS similarity.
    thread_export.py    Thread tree traversal and JSONL export for training data.
    visualization.py    Plotly interactive figure generation for graphs.
    scraping.py         Legacy Pushshift scraper (largely non-functional post-2023).
clustering/             Git submodule: spectral/hierarchical clustering utilities.
                        Must be initialised before running 08_user_clustering.ipynb.
data/                   Input data files (gitignored -- add files manually).
output/                 Generated figures, exported JSONL, HTML visualisations.
archive/                Notebooks for other subreddits, not part of main pipeline.
01_scraping.ipynb               Pipeline step 1: data collection.
02_data_loading.ipynb           Pipeline step 2: zstd to Parquet conversion.
03_eda.ipynb                    Pipeline step 3: exploratory temporal analysis.
04_word_frequency.ipynb         Pipeline step 4: NLTK word frequency (Italian NLP).
05_nlp.ipynb                    Pipeline step 5: NLP analysis (originally on Colab).
06_posting_habits.ipynb         Pipeline step 6: per-user posting patterns.
07_network_analysis.ipynb       Pipeline step 7: interaction graphs, PageRank.
08_user_clustering.ipynb        Pipeline step 8: TF-IDF and spectral clustering.
09_thread_export.ipynb          Pipeline step 9: conversation chain export.
```

## Setup

This project uses [uv](https://docs.astral.sh/uv/) for dependency management
and requires Python 3.13.

```bash
# Install dependencies
uv sync

# Initialise the clustering submodule (required for 08_user_clustering.ipynb)
git submodule update --init --recursive

# Launch Jupyter
uv run jupyter lab
```

## Data

Data files are gitignored and must be added manually. The expected input is a
zstandard-compressed newline-delimited JSON file of Reddit comments:

    data/litigi_comments.zst

Run `02_data_loading.ipynb` to convert it to Parquet format. Subsequent notebooks
expect:

    data/litigi_comments.parquet

All file paths in notebooks use `pathlib.Path` relative to the repository root.
Do not use absolute or platform-specific paths.

## Development Guidelines

- All reusable logic belongs in `functions/`. Notebooks should import from
  `functions` rather than defining their own implementations of analysis functions.
- Docstrings follow Google style (Args / Returns / Raises / Example sections).
- All functions must have type annotations.
- Use `pathlib.Path` for all file paths.
- Use `uv add <package>` to add dependencies. Do not use `!pip install` in
  notebooks intended for local execution.
- No emojis in code, docstrings, or documentation.
- The `clustering/` directory is a git submodule pointing to a separate repository.
  Do not commit changes to it from this repository.

## Optional Dependencies

The following packages are used in specific notebooks but are not listed in
`pyproject.toml` because they are either optional or may be unavailable:

- `pyvis` -- interactive HTML network visualisation (07_network_analysis.ipynb)
- `nltk` -- Italian tokenisation and stemming (04_word_frequency.ipynb)
- `scikit-learn` -- TF-IDF, PCA, LDA (08_user_clustering.ipynb)
- `minisom` -- Self-Organising Maps (08_user_clustering.ipynb)
- `stop-words` -- multilingual stopword lists
- `pmaw` -- Pushshift API wrapper (01_scraping.ipynb, largely non-functional)

Install individually as needed: `uv add <package>`.

## Known Issues

- `05_nlp.ipynb` was originally developed in Google Colab and contains
  Colab-specific file paths. Update path variables at the top of the notebook
  before running locally.
- `08_user_clustering.ipynb` requires the `clustering/` submodule to be
  initialised. The notebook will fail to import until the submodule is populated.
- The Pushshift API used in `01_scraping.ipynb` has been heavily restricted since
  mid-2023. For current data collection, use Arctic Shift archives and load with
  `functions.io.extract_zstd()`.

## Thread Export for Bot Training

The thread export pipeline converts Reddit comment trees into training data:

```python
from pathlib import Path
from functions import load_comments, create_nx_graph
from functions.thread_export import (
    extract_thread_chains,
    export_chains_to_jsonl,
    chains_to_prompt_pairs,
    export_prompt_pairs_to_jsonl,
)

df = load_comments(Path("data/litigi_comments.parquet"))
G = create_nx_graph(df)

# Extract all conversation chains of depth >= 2
chains = extract_thread_chains(G, df, min_length=2)

# Export full chains (one per thread path)
export_chains_to_jsonl(chains, Path("output/litigi_threads.jsonl"))

# Convert to prompt/response pairs for SFT
pairs = chains_to_prompt_pairs(chains, system_prompt="Sei un utente di r/litigi.")
export_prompt_pairs_to_jsonl(pairs, Path("output/litigi_pairs.jsonl"))
```

See `09_thread_export.ipynb` for a complete walkthrough.
