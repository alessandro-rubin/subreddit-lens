"""Command-line interface for subreddit-lens.

Every analysis command reads a TOML configuration (see subreddit_lens.config)
and accepts options that override it. Typical session:

    subreddit-lens init litigi --timezone Europe/Rome --language it
    subreddit-lens ingest
    subreddit-lens network
    subreddit-lens metrics
    subreddit-lens habits
    subreddit-lens export

or everything at once with 'subreddit-lens run'.
"""

import dataclasses
import logging
from collections.abc import Callable
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any

import typer
import zstandard as zstd

from subreddit_lens import __version__, pipeline
from subreddit_lens.config import Config, load_config

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


@app.command()
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


@app.command()
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


@app.command()
def network(
    config: ConfigOption = DEFAULT_CONFIG,
    data_dir: DataDirOption = None,
    output_dir: OutputDirOption = None,
) -> None:
    """Build the user interaction graph (GraphML)."""
    cfg = _load(config, data_dir=data_dir, output_dir=output_dir)
    path = _run(lambda: pipeline.run_network(cfg))
    typer.echo(f"User graph -> {path}")


@app.command()
def metrics(
    config: ConfigOption = DEFAULT_CONFIG,
    output_dir: OutputDirOption = None,
    seed: Annotated[int, typer.Option(help="Random seed for community detection.")] = 0,
) -> None:
    """Compute per-user network metrics (CSV)."""
    cfg = _load(config, output_dir=output_dir)
    path = _run(lambda: pipeline.run_metrics(cfg, community_seed=seed))
    typer.echo(f"User metrics -> {path}")


@app.command()
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


@app.command()
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


@app.command()
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
