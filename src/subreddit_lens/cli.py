"""Command-line interface for subreddit-lens.

Only the application skeleton exists for now; the pipeline commands
(ingest, habits, network, metrics, export, app) are added in Phase 5 of
docs/ROADMAP.md.
"""

import typer

from subreddit_lens import __version__

app = typer.Typer(
    name="subreddit-lens",
    help="Explore and analyse user interactions in a subreddit.",
    no_args_is_help=True,
)


@app.callback()
def main() -> None:
    """Explore and analyse user interactions in a subreddit."""


@app.command()
def version() -> None:
    """Print the installed version."""
    typer.echo(__version__)
