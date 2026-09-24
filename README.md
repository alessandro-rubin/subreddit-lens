# subreddit-lens

Explore and analyse user interactions in a subreddit.

`subreddit-lens` is a Python package for working with Reddit comment archives
(Pushshift / Arctic Shift dumps). Once the data is ingested, you can explore
it from Python, from the command line, with SQL, or through an AI assistant
(via the Model Context Protocol, see below). It covers three areas:

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
| `viz`        | matplotlib, seaborn, pyvis                    | static plots, HTML network views  |
| `som`        | minisom                                       | self-organising maps              |
| `mcp`        | mcp                                           | serving the data to AI assistants |
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
uv run pre-commit install # ruff, mypy and nbstripout on every commit
uv run pytest --cov
uv run ruff check && uv run mypy
uv run jupyter lab        # to run the example notebooks
```

## Quick start

Describe the subreddit in a small TOML file (see
`examples/litigi/subreddit-lens.toml`):

```toml
subreddit = "litigi"
timezone = "Europe/Rome"
language = "it"
data_dir = "data"
```

Then:

```python
from subreddit_lens import (
    create_nx_graph,
    extract_interaction_graph,
    extract_thread_chains,
    get_parent_author,
    ingest_archive,
    load_comments,
    load_config,
    load_submissions,
    save_graph,
    user_metrics,
)

config = load_config("subreddit-lens.toml")

# 1. Stream the archives to Parquet (memory use is bounded by chunk_size).
ingest_archive(config.comments_archive, config.comments_parquet)
ingest_archive(config.submissions_archive, config.submissions_parquet, "submissions")

comments = load_comments(config.comments_parquet)
submissions = load_submissions(config.submissions_parquet)

# 2. Who replies to whom, including replies to the author of each post.
users = extract_interaction_graph(
    get_parent_author(comments, submissions),
    exclude_authors=config.exclude_authors,
)
save_graph(users, config.output_dir / "users.graphml")  # also opens in Gephi

# 3. One row per user: replies sent/received, reciprocity, PageRank,
#    h-index, community.
metrics = user_metrics(users)

# 4. Conversation chains.
threads = create_nx_graph(comments)
chains = extract_thread_chains(threads, comments, min_length=2)
```

## Command line

The whole pipeline runs from the terminal, driven by the configuration file:

```bash
uv run subreddit-lens init litigi --timezone Europe/Rome --language it
# put litigi_comments.zst (and optionally litigi_submissions.zst) in data/
uv run subreddit-lens ingest     # archives -> Parquet (chunked)
uv run subreddit-lens network    # -> output/litigi_users.graphml
uv run subreddit-lens metrics    # -> output/litigi_user_metrics.csv
uv run subreddit-lens habits     # -> output/litigi_habits.parquet
uv run subreddit-lens export     # -> output/litigi_threads.jsonl, litigi_pairs.jsonl
```

`uv run subreddit-lens run` does all of the above in one go (`--skip-ingest`
reuses existing Parquet files). Every command takes `--config FILE` (default
`subreddit-lens.toml` in the current directory) and options that override it,
e.g. `ingest --start 2023-01-01`, `habits --timezone UTC --min-posts 20`,
`export --format pairs --preprocess --system-prompt "..."`. Add `-v` before
the command for progress messages, and `--help` after any command for its
options. For the r/litigi example:

```bash
uv run subreddit-lens run --config examples/litigi/subreddit-lens.toml
```

The same steps are available from Python as `subreddit_lens.pipeline.run_*`.

## Exploring the data

After `ingest`, the explore commands answer common questions directly. They
query the Parquet files through [DuckDB](https://duckdb.org/), so they are
fast even on large subreddits and need no other step (PageRank rankings
also need `network` and `metrics`):

```bash
uv run subreddit-lens summary                      # counts, time span, busiest times
uv run subreddit-lens users --by replies_received  # also comments, score, pagerank, ...
uv run subreddit-lens user some_username           # activity, habits, interlocutors
uv run subreddit-lens activity --by weekday        # or hour, day, month (local time)
uv run subreddit-lens threads --by authors         # then: subreddit-lens thread <id>
uv run subreddit-lens search "avvocato" -n 20
uv run subreddit-lens interactions --author some_username
uv run subreddit-lens schema                       # SQL views and columns
uv run subreddit-lens sql "SELECT author, count(*) AS n FROM comments GROUP BY 1 ORDER BY 2 DESC"
```

Tables are printed for people; add `--json` for machine-readable output.
`subreddit-lens guide` prints a short description of the views, the ID
conventions and example queries.

From Python, `Explorer` offers the same analyses and returns DataFrames:

```python
from subreddit_lens import Explorer

with Explorer.from_config("subreddit-lens.toml") as ex:
    ex.summary()
    ex.top_users("replies_received", n=10)
    ex.user("some_username")
    ex.thread("1abc23")
    ex.sql("""
        SELECT date_trunc('month', created_at) AS month, count(*) AS comments
        FROM comments GROUP BY 1 ORDER BY 1
    """)
```

The SQL views are `comments`, `submissions`, `replies` (each comment with
the author it replies to), `users`, `threads`, `user_metrics` (after the
`metrics` step) and `excluded_authors`. Only single `SELECT` statements are
accepted, and DuckDB can read only the configured data and output
directories.

## Use with AI assistants

`subreddit-lens mcp` serves the explore tools over the
[Model Context Protocol](https://modelcontextprotocol.io/), so an assistant
such as Claude can answer questions about the subreddit by calling them.
All tools are read-only; the server also sends the guide as its
instructions, so the assistant knows the views and conventions without
reading the code. Install the `mcp` extra (included in the development
setup), run `ingest` first, and use absolute paths, since the client starts
the server from its own working directory.

Claude Code:

```bash
claude mcp add subreddit-lens -- \
    uv run --directory /path/to/reddit_stuff \
    subreddit-lens mcp --config /path/to/subreddit-lens.toml
```

Claude Desktop and other clients that use an `mcpServers` JSON file:

```json
{
  "mcpServers": {
    "subreddit-lens": {
      "command": "uvx",
      "args": [
        "--from", "subreddit-lens[mcp] @ git+https://github.com/alessandro-rubin/reddit_stuff",
        "subreddit-lens", "mcp", "--config", "/path/to/subreddit-lens.toml"
      ]
    }
  }
}
```

Tools: `summary`, `schema`, `top_users`, `user_profile`, `activity`,
`top_threads`, `thread`, `search`, `interactions`, `run_sql`. Results are
capped (at most 5,000 rows, comment bodies truncated by default), and
errors such as a misspelt username come back with suggestions the assistant
can act on.

An assistant working in a terminal can also use the CLI directly: `guide`
explains the data and every command accepts `--json`.

Keep in mind that whatever the tools return (usernames, comment text) is
sent to the assistant's provider.

## Data

Data files are not part of the repository. Download a subreddit's comments
and, optionally, submissions from the
[Arctic Shift](https://github.com/ArthurHeitmann/arctic_shift) project as
zstd-compressed NDJSON files and place them in the data directory, named
after the subreddit:

```
data/litigi_comments.zst         -> required
data/litigi_submissions.zst      -> optional, needed for replies to post authors
data/litigi_comments.parquet     -> produced by ingest_archive()
data/litigi_submissions.parquet  -> produced by ingest_archive()
```

`examples/litigi/02_data_loading.ipynb` runs the ingestion for r/litigi.
Without submissions, the author of a post is inferred from comments that
Reddit flags with `is_submitter`, so replies to authors who never commented
in their own thread are missing from the interaction graph.

## Repository layout

```
src/subreddit_lens/   the package
    config.py         per-subreddit settings (TOML)
    explore.py        Explorer: DuckDB views and ready-made analyses
    guide.py          usage guide shared by the CLI and the MCP server
    mcp_server.py     MCP server for AI assistants
    io/               zstd archives, schema, chunked ingestion, Parquet readers
    text/             comment text cleaning
    network/          thread graphs, user interaction graphs, metrics, storage
    temporal/         posting-habit KDEs and similarity
    export/           thread chains and prompt/response pairs (JSONL)
    viz/              Plotly figures
    legacy/           old Pushshift scraper (unsupported)
    pipeline.py       pipeline steps driven by the config (used by the CLI)
    cli.py            command-line interface
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
