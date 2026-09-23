# subreddit-lens

Explore and analyse user interactions in a subreddit.

`subreddit-lens` is a Python package for working with Reddit comment archives
(Pushshift / Arctic Shift dumps). It covers three areas:

1. **Posting habits** -- when users are active (hour of day, weekday, month),
   estimated with periodic kernel density estimation, and how similar users
   are to each other (Jensen-Shannon).
2. **Social network analysis** -- who replies to whom: weighted user
   interaction graphs, PageRank, h-index, community visualisation.
3. **Thread export** -- conversation trees exported as JSONL chains or
   prompt/response pairs.

The project started as an analysis of r/litigi, an Italian-language
subreddit; that analysis is kept as a worked example in `examples/litigi/`.

> Status: alpha. The package is being restructured following
> [docs/ROADMAP.md](docs/ROADMAP.md). The API may change.

## Installation

Requires Python 3.13 or later. With [uv](https://docs.astral.sh/uv/):

```bash
uv add git+https://github.com/alessandro-rubin/reddit_stuff
```

Optional features are grouped as extras:

| Extra        | Adds                                          | Used for                          |
|--------------|-----------------------------------------------|-----------------------------------|
| `nlp`        | nltk, scikit-learn, stop-words                | word frequencies, TF-IDF, LDA     |
| `sentiment`  | transformers, torch, datasets, tqdm           | sentiment classification          |
| `embeddings` | sentence-transformers                         | sentence embeddings (pulls PyTorch) |
| `viz`        | matplotlib, seaborn, pyvis, wordcloud         | static plots, HTML network views  |
| `som`        | minisom                                       | self-organising maps              |
| `legacy`     | pmaw                                          | old Pushshift scraper             |
| `all`        | everything except `legacy`                    |                                   |

```bash
uv add "subreddit-lens[nlp,viz] @ git+https://github.com/alessandro-rubin/reddit_stuff"
```

## Development setup

```bash
git clone https://github.com/alessandro-rubin/reddit_stuff
cd reddit_stuff
uv sync --all-extras      # or pick extras: uv sync --extra viz
uv run pytest
uv run ruff check
uv run jupyter lab        # to run the example notebooks
```

## Quick start

```python
from pathlib import Path

import networkx as nx

from subreddit_lens import (
    create_nx_graph,
    extract_interaction_graph,
    extract_thread_chains,
    get_parent_author,
    load_comments,
)

df = load_comments(Path("data/litigi_comments.parquet"))

# Who replies to whom
users = extract_interaction_graph(get_parent_author(df))
influence = nx.pagerank(users.reverse(), weight="weight")

# Conversation chains
threads = create_nx_graph(df)
chains = extract_thread_chains(threads, df, min_length=2)
```

A command-line interface is being built; for now it only reports the
version:

```bash
uv run subreddit-lens version
```

## Data

Data files are not part of the repository. Download a subreddit's comments
from the [Arctic Shift](https://github.com/ArthurHeitmann/arctic_shift)
project as a zstd-compressed NDJSON file, place it in `data/`, and convert it
with `examples/litigi/02_data_loading.ipynb`:

```
data/litigi_comments.zst      -> input archive
data/litigi_comments.parquet  -> produced by 02_data_loading.ipynb
```

## Repository layout

```
src/subreddit_lens/   the package
    io/               zstd archive and Parquet readers
    text/             comment text cleaning
    network/          thread graphs, user interaction graphs, metrics
    temporal/         posting-habit KDEs and similarity
    export/           thread chains and prompt/response pairs (JSONL)
    clustering/       spectral and hierarchical clustering helpers
    viz/              Plotly figures
    legacy/           old Pushshift scraper (unsupported)
    cli.py            command-line entry point
examples/litigi/      the r/litigi analysis notebooks (01-09)
examples/archive/     notebooks for other subreddits
tests/                pytest suite
docs/                 roadmap and documentation
```

## Legal and ethical notes

- Reddit usernames are pseudonymous personal data; for EU users the GDPR
  applies. Do not redistribute raw dumps, and hash usernames in anything you
  publish.
- Reddit's User Agreement and Data API Terms restrict using Reddit content to
  train machine-learning models without an agreement with Reddit, regardless
  of whether the data came from an archive. Check the current terms before
  using the thread export output beyond personal research.

## License

MIT, see [LICENSE](LICENSE).
