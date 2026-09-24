"""Command-line interface for subreddit-lens.

Every analysis command reads a TOML configuration (see subreddit_lens.config)
and accepts options that override it. Typical session:

    subreddit-lens init litigi --timezone Europe/Rome --language it
    subreddit-lens ingest
    subreddit-lens network
    subreddit-lens metrics
    subreddit-lens habits
    subreddit-lens export

or everything at once with 'subreddit-lens run'. Then explore:

    subreddit-lens summary
    subreddit-lens users --by replies_received
    subreddit-lens user SOMEONE
    subreddit-lens sql "SELECT ..."

Exploration commands accept --json for machine-readable output, and
'subreddit-lens mcp' serves the same analyses to AI assistants over MCP.
"""

import dataclasses
import logging
from collections.abc import Callable
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any, cast

import typer
import zstandard as zstd

from subreddit_lens import __version__, pipeline
from subreddit_lens.config import Config, load_config
from subreddit_lens.explore import Explorer, to_json
from subreddit_lens.guide import GUIDE

DEFAULT_CONFIG = Path("subreddit-lens.toml")

app = typer.Typer(
    name="subreddit-lens",
    help="Explore and analyse user interactions in a subreddit.",
    no_args_is_help=True,
    add_completion=False,
)

ConfigOption = Annotated[
    Path,
    typer.Option("--config", "-c", help="TOML configuration file."),
]
DataDirOption = Annotated[
    Path | None,
    typer.Option(help="Override the configured data directory."),
]
OutputDirOption = Annotated[
    Path | None,
    typer.Option(help="Override the configured output directory."),
]


JsonOption = Annotated[
    bool, typer.Option("--json", help="Print JSON instead of a table.")
]
LimitOption = Annotated[int, typer.Option("--n", "-n", min=1, help="Number of rows.")]
CharsOption = Annotated[
    int, typer.Option(min=1, help="Maximum characters per comment body.")
]

PIPELINE = "Pipeline"
EXPLORE = "Explore"
AI = "AI assistants"


class UserBy(StrEnum):
    """Rankings accepted by the users command."""

    comments = "comments"
    submissions = "submissions"
    threads = "threads"
    score = "score"
    replies_received = "replies_received"
    replies_sent = "replies_sent"
    pagerank = "pagerank"


class Period(StrEnum):
    """Periods accepted by the activity command."""

    hour = "hour"
    weekday = "weekday"
    day = "day"
    month = "month"


class ThreadBy(StrEnum):
    """Rankings accepted by the threads command."""

    comments = "comments"
    authors = "authors"
    recent = "recent"


class ExportFormat(StrEnum):
    """What the export command writes."""

    chains = "chains"
    pairs = "pairs"
    both = "both"


@app.callback()
def main(
    verbose: Annotated[
        bool, typer.Option("--verbose", "-v", help="Show progress messages.")
    ] = False,
) -> None:
    """Explore and analyse user interactions in a subreddit."""
    logging.basicConfig(
        level=logging.INFO if verbose else logging.WARNING,
        format="%(levelname)s %(message)s",
        force=True,
    )


def _fail(message: str) -> typer.Exit:
    typer.secho(f"Error: {message}", fg=typer.colors.RED, err=True)
    return typer.Exit(code=1)


def _load(config_path: Path, **overrides: Any) -> Config:
    """Load the configuration and apply the command-line overrides."""
    if not config_path.exists():
        raise _fail(
            f"{config_path} not found. Create one with "
            "'subreddit-lens init SUBREDDIT' or pass --config."
        )
    try:
        config = load_config(config_path)
        changes = {k: v for k, v in overrides.items() if v is not None}
        return dataclasses.replace(config, **changes)
    except ValueError as exc:  # includes TOMLDecodeError
        raise _fail(str(exc)) from exc


def _run[T](step: Callable[[], T]) -> T:
    """Run a pipeline step, turning expected errors into a clean exit."""
    try:
        return step()
    except (FileNotFoundError, ValueError) as exc:
        raise _fail(str(exc)) from exc
    except zstd.ZstdError as exc:
        raise _fail(f"Corrupt or truncated archive: {exc}") from exc


def _parse_date(value: str | None, name: str) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise _fail(f"--{name} must be a date (YYYY-MM-DD), got {value!r}") from exc


@app.command()
def version() -> None:
    """Print the installed version."""
    typer.echo(__version__)


@app.command(rich_help_panel=PIPELINE)
def init(
    subreddit: Annotated[str, typer.Argument(help="Subreddit name, without r/.")],
    path: ConfigOption = DEFAULT_CONFIG,
    timezone: Annotated[str, typer.Option(help="IANA timezone.")] = "UTC",
    language: Annotated[str, typer.Option(help="ISO 639-1 code.")] = "en",
    force: Annotated[
        bool, typer.Option("--force", help="Overwrite an existing file.")
    ] = False,
) -> None:
    """Write a starter configuration file."""
    try:
        Config(subreddit, timezone=timezone, language=language)
    except ValueError as exc:
        raise _fail(str(exc)) from exc
    if path.exists() and not force:
        raise _fail(f"{path} already exists (use --force to overwrite).")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f'subreddit = "{subreddit}"\n'
        f'timezone = "{timezone}"\n'
        f'language = "{language}"\n'
        "# Paths are relative to this file.\n"
        'data_dir = "data"\n'
        'output_dir = "output"\n'
        "# Optional inclusive date range (UTC days):\n"
        "# start = 2020-01-01\n"
        "# end = 2024-12-31\n"
        'exclude_authors = ["[deleted]", "AutoModerator"]\n',
        encoding="utf-8",
    )
    typer.echo(f"Wrote {path}. Put {subreddit}_comments.zst in the data directory.")


@app.command(rich_help_panel=PIPELINE)
def ingest(
    config: ConfigOption = DEFAULT_CONFIG,
    data_dir: DataDirOption = None,
    start: Annotated[
        str | None, typer.Option(help="First day to keep (YYYY-MM-DD).")
    ] = None,
    end: Annotated[
        str | None, typer.Option(help="Last day to keep (YYYY-MM-DD).")
    ] = None,
    chunk_size: Annotated[
        int, typer.Option(min=1, help="Records held in memory per chunk.")
    ] = pipeline.DEFAULT_CHUNK_SIZE,
    extra_column: Annotated[
        list[str] | None,
        typer.Option(help="Extra comment field to keep; repeatable."),
    ] = None,
) -> None:
    """Convert the comment (and submission) archives to Parquet."""
    cfg = _load(
        config,
        data_dir=data_dir,
        start=_parse_date(start, "start"),
        end=_parse_date(end, "end"),
    )
    result = _run(
        lambda: pipeline.run_ingest(
            cfg, chunk_size=chunk_size, extra_columns=extra_column or ()
        )
    )
    typer.echo(f"{result.comments:,} comments -> {cfg.comments_parquet}")
    if result.submissions is None:
        typer.echo(f"No submissions archive ({cfg.submissions_archive}): skipped.")
    else:
        typer.echo(f"{result.submissions:,} submissions -> {cfg.submissions_parquet}")


@app.command(rich_help_panel=PIPELINE)
def network(
    config: ConfigOption = DEFAULT_CONFIG,
    data_dir: DataDirOption = None,
    output_dir: OutputDirOption = None,
) -> None:
    """Build the user interaction graph (GraphML)."""
    cfg = _load(config, data_dir=data_dir, output_dir=output_dir)
    path = _run(lambda: pipeline.run_network(cfg))
    typer.echo(f"User graph -> {path}")


@app.command(rich_help_panel=PIPELINE)
def metrics(
    config: ConfigOption = DEFAULT_CONFIG,
    output_dir: OutputDirOption = None,
    seed: Annotated[int, typer.Option(help="Random seed for community detection.")] = 0,
) -> None:
    """Compute per-user network metrics (CSV)."""
    cfg = _load(config, output_dir=output_dir)
    path = _run(lambda: pipeline.run_metrics(cfg, community_seed=seed))
    typer.echo(f"User metrics -> {path}")


@app.command(rich_help_panel=PIPELINE)
def habits(
    config: ConfigOption = DEFAULT_CONFIG,
    data_dir: DataDirOption = None,
    output_dir: OutputDirOption = None,
    timezone: Annotated[
        str | None, typer.Option(help="Override the configured timezone.")
    ] = None,
    min_posts: Annotated[int, typer.Option(min=2, help="Minimum posts per user.")] = 10,
    resolution: Annotated[
        int, typer.Option(help="Grid spacing in minutes (divisor of 60).")
    ] = 15,
) -> None:
    """Estimate hourly posting densities per user (Parquet)."""
    cfg = _load(config, data_dir=data_dir, output_dir=output_dir, timezone=timezone)
    path = _run(
        lambda: pipeline.run_habits(
            cfg, min_posts=min_posts, resolution_minutes=resolution
        )
    )
    typer.echo(f"Posting habits -> {path}")


@app.command(rich_help_panel=PIPELINE)
def export(
    config: ConfigOption = DEFAULT_CONFIG,
    data_dir: DataDirOption = None,
    output_dir: OutputDirOption = None,
    what: Annotated[
        ExportFormat, typer.Option("--format", help="What to write.")
    ] = ExportFormat.both,
    min_length: Annotated[
        int, typer.Option(min=2, help="Minimum comments per chain.")
    ] = 2,
    system_prompt: Annotated[
        str, typer.Option(help="System prompt added to every pair.")
    ] = "",
    clean: Annotated[
        bool,
        typer.Option(
            "--preprocess",
            help="Clean comment text (HTML entities, quotes, Markdown links).",
        ),
    ] = False,
) -> None:
    """Export conversation chains and prompt/response pairs (JSONL)."""
    cfg = _load(config, data_dir=data_dir, output_dir=output_dir)
    paths = _run(
        lambda: pipeline.run_export(
            cfg,
            min_length=min_length,
            system_prompt=system_prompt,
            chains=what in (ExportFormat.chains, ExportFormat.both),
            pairs=what in (ExportFormat.pairs, ExportFormat.both),
            clean_text=clean,
        )
    )
    for path in paths:
        typer.echo(f"Export -> {path}")


@app.command(rich_help_panel=PIPELINE)
def run(
    config: ConfigOption = DEFAULT_CONFIG,
    data_dir: DataDirOption = None,
    output_dir: OutputDirOption = None,
    skip_ingest: Annotated[
        bool,
        typer.Option("--skip-ingest", help="Reuse existing Parquet files."),
    ] = False,
) -> None:
    """Run the whole pipeline: ingest, network, metrics, habits, export."""
    cfg = _load(config, data_dir=data_dir, output_dir=output_dir)
    steps: list[tuple[str, Callable[[], object]]] = [
        ("network", lambda: pipeline.run_network(cfg)),
        ("metrics", lambda: pipeline.run_metrics(cfg)),
        ("habits", lambda: pipeline.run_habits(cfg)),
        ("export", lambda: pipeline.run_export(cfg)),
    ]
    if not skip_ingest:
        steps.insert(0, ("ingest", lambda: pipeline.run_ingest(cfg)))
    for name, step in steps:
        typer.echo(f"[{name}]")
        _run(step)
    typer.echo(f"Done. Outputs in {cfg.output_dir}")


# -- exploration ---------------------------------------------------------------


def _explorer(config: Path, data_dir: Path | None, output_dir: Path | None) -> Explorer:
    cfg = _load(config, data_dir=data_dir, output_dir=output_dir)
    return _run(lambda: Explorer(cfg))


def _emit(result: Any, as_json: bool) -> None:
    """Print a DataFrame as a table (or JSON) and anything else as JSON."""
    if as_json or not hasattr(result, "to_string"):
        typer.echo(to_json(result))
    elif result.empty:
        typer.echo("(no rows)")
    else:
        typer.echo(result.to_string(index=False, max_colwidth=80))


@app.command(rich_help_panel=EXPLORE)
def summary(
    config: ConfigOption = DEFAULT_CONFIG,
    data_dir: DataDirOption = None,
    output_dir: OutputDirOption = None,
) -> None:
    """Overview: counts, time span, busiest times, top commenters (JSON)."""
    with _explorer(config, data_dir, output_dir) as ex:
        _emit(_run(ex.summary), as_json=True)


@app.command(rich_help_panel=EXPLORE)
def users(
    config: ConfigOption = DEFAULT_CONFIG,
    data_dir: DataDirOption = None,
    output_dir: OutputDirOption = None,
    by: Annotated[UserBy, typer.Option(help="Ranking.")] = UserBy.comments,
    n: LimitOption = 20,
    as_json: JsonOption = False,
) -> None:
    """Top users by activity, replies or PageRank."""
    with _explorer(config, data_dir, output_dir) as ex:
        _emit(_run(lambda: ex.top_users(cast(Any, by.value), n)), as_json)


@app.command(rich_help_panel=EXPLORE)
def user(
    author: Annotated[str, typer.Argument(help="Username (case-sensitive).")],
    config: ConfigOption = DEFAULT_CONFIG,
    data_dir: DataDirOption = None,
    output_dir: OutputDirOption = None,
    max_chars: CharsOption = 300,
) -> None:
    """Profile of one user (JSON)."""
    with _explorer(config, data_dir, output_dir) as ex:
        _emit(_run(lambda: ex.user(author, max_chars)), as_json=True)


@app.command(rich_help_panel=EXPLORE)
def activity(
    config: ConfigOption = DEFAULT_CONFIG,
    data_dir: DataDirOption = None,
    output_dir: OutputDirOption = None,
    by: Annotated[Period, typer.Option(help="Period.")] = Period.hour,
    author: Annotated[str | None, typer.Option(help="Restrict to one user.")] = None,
    as_json: JsonOption = False,
) -> None:
    """Comments per hour, weekday, day or month (local time)."""
    with _explorer(config, data_dir, output_dir) as ex:
        _emit(_run(lambda: ex.activity(cast(Any, by.value), author)), as_json)


@app.command(rich_help_panel=EXPLORE)
def threads(
    config: ConfigOption = DEFAULT_CONFIG,
    data_dir: DataDirOption = None,
    output_dir: OutputDirOption = None,
    by: Annotated[ThreadBy, typer.Option(help="Ranking.")] = ThreadBy.comments,
    n: LimitOption = 20,
    as_json: JsonOption = False,
) -> None:
    """Top threads by comments, authors or recency."""
    with _explorer(config, data_dir, output_dir) as ex:
        _emit(_run(lambda: ex.top_threads(cast(Any, by.value), n)), as_json)


@app.command(rich_help_panel=EXPLORE)
def thread(
    thread_id: Annotated[str, typer.Argument(help="Submission ID.")],
    config: ConfigOption = DEFAULT_CONFIG,
    data_dir: DataDirOption = None,
    output_dir: OutputDirOption = None,
    n: LimitOption = 500,
    max_chars: CharsOption = 300,
    as_json: JsonOption = False,
) -> None:
    """A thread's comments in reading order, with nesting depth."""
    with _explorer(config, data_dir, output_dir) as ex:
        _emit(_run(lambda: ex.thread(thread_id, n, max_chars)), as_json)


@app.command(rich_help_panel=EXPLORE)
def search(
    text: Annotated[str, typer.Argument(help="Text to find (case-insensitive).")],
    config: ConfigOption = DEFAULT_CONFIG,
    data_dir: DataDirOption = None,
    output_dir: OutputDirOption = None,
    author: Annotated[str | None, typer.Option(help="Restrict to one user.")] = None,
    n: LimitOption = 20,
    max_chars: CharsOption = 300,
    as_json: JsonOption = False,
) -> None:
    """Comments containing a text, newest first."""
    with _explorer(config, data_dir, output_dir) as ex:
        _emit(_run(lambda: ex.search(text, n, author, max_chars)), as_json)


@app.command(rich_help_panel=EXPLORE)
def interactions(
    config: ConfigOption = DEFAULT_CONFIG,
    data_dir: DataDirOption = None,
    output_dir: OutputDirOption = None,
    author: Annotated[
        str | None, typer.Option(help="Only pairs involving this user.")
    ] = None,
    n: LimitOption = 20,
    as_json: JsonOption = False,
) -> None:
    """Strongest reply relationships between users."""
    with _explorer(config, data_dir, output_dir) as ex:
        _emit(_run(lambda: ex.interactions(author, n)), as_json)


@app.command(rich_help_panel=EXPLORE)
def sql(
    query: Annotated[str, typer.Argument(help="One DuckDB SELECT statement.")],
    config: ConfigOption = DEFAULT_CONFIG,
    data_dir: DataDirOption = None,
    output_dir: OutputDirOption = None,
    limit: Annotated[int, typer.Option(min=1, help="Maximum rows.")] = 1000,
    as_json: JsonOption = False,
) -> None:
    """Run a read-only SQL query (see 'schema' for the views)."""
    with _explorer(config, data_dir, output_dir) as ex:
        _emit(_run(lambda: ex.sql(query, limit)), as_json)


@app.command(rich_help_panel=EXPLORE)
def schema(
    config: ConfigOption = DEFAULT_CONFIG,
    data_dir: DataDirOption = None,
    output_dir: OutputDirOption = None,
) -> None:
    """List the SQL views and their columns (JSON)."""
    with _explorer(config, data_dir, output_dir) as ex:
        _emit(_run(ex.schema), as_json=True)


# -- AI assistants -------------------------------------------------------------


@app.command(rich_help_panel=AI)
def guide() -> None:
    """Print the usage guide for people and AI assistants."""
    typer.echo(GUIDE)


@app.command(rich_help_panel=AI)
def mcp(
    config: ConfigOption = DEFAULT_CONFIG,
    data_dir: DataDirOption = None,
    output_dir: OutputDirOption = None,
) -> None:
    """Serve the exploration tools to AI assistants over MCP (stdio)."""
    try:
        from subreddit_lens.mcp_server import build_server
    except ImportError as exc:
        raise _fail(
            "The MCP server needs the 'mcp' extra: "
            "uv add 'subreddit-lens[mcp]' (or uv sync --extra mcp)."
        ) from exc
    with _explorer(config, data_dir, output_dir) as ex:
        build_server(ex).run("stdio")
