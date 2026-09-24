"""MCP server exposing the Explorer to AI assistants.

Run it with 'subreddit-lens mcp --config subreddit-lens.toml' and register
that command in an MCP client (Claude Desktop, Claude Code, ...). Every tool
is read-only; results are JSON. Requires the 'mcp' extra:

    uv add "subreddit-lens[mcp]"
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from subreddit_lens import __version__
from subreddit_lens.explore import (
    DEFAULT_MAX_CHARS,
    DEFAULT_SQL_LIMIT,
    ActivityPeriod,
    Explorer,
    ThreadRanking,
    UserRanking,
    to_jsonable,
)
from subreddit_lens.guide import GUIDE

_READ_ONLY = ToolAnnotations(
    read_only_hint=True,
    destructive_hint=False,
    idempotent_hint=True,
    open_world_hint=False,
)

# Upper bounds on sizes an assistant can request in one call.
_MAX_ROWS = 5000
_MAX_CHARS = 10_000


@contextmanager
def _expected_errors() -> Iterator[None]:
    """Report expected errors (bad SQL, unknown user, missing data) to the model.

    The MCP SDK hides the text of arbitrary exceptions from the client; a
    ToolError keeps it, so the assistant sees e.g. 'Only SELECT queries are
    allowed' or the list of similar usernames and can correct its call.
    """
    try:
        yield
    except (ValueError, FileNotFoundError) as exc:
        raise ToolError(str(exc)) from exc


def _rows(n: int) -> int:
    return max(1, min(n, _MAX_ROWS))


def _chars(n: int) -> int:
    return max(1, min(n, _MAX_CHARS))


def build_server(explorer: Explorer) -> MCPServer:
    """Create an MCP server whose tools query the given Explorer.

    Args:
        explorer: An open Explorer; the server does not close it.

    Returns:
        The configured server; call .run() to serve over stdio.
    """
    subreddit = explorer.config.subreddit
    server: MCPServer = MCPServer(
        name="subreddit-lens",
        title=f"r/{subreddit} explorer",
        description=f"Read-only analytics over r/{subreddit} comments.",
        instructions=GUIDE,
        version=__version__,
    )

    @server.tool(annotations=_READ_ONLY)
    def summary() -> dict[str, Any]:
        """Overview of the dataset: counts, time span, busiest times, top users.

        Call this first. It also says whether submissions and network metrics
        are available.
        """
        with _expected_errors():
            result: dict[str, Any] = to_jsonable(explorer.summary())
        return result

    @server.tool(annotations=_READ_ONLY)
    def schema() -> dict[str, Any]:
        """List the SQL views and their columns, for use with run_sql."""
        with _expected_errors():
            return {"views": explorer.schema()}

    @server.tool(annotations=_READ_ONLY)
    def top_users(by: UserRanking = "comments", n: int = 20) -> list[dict[str, Any]]:
        """Rank users.

        Args:
            by: comments, submissions, threads, score, replies_received,
                replies_sent, or pagerank (influence; needs network metrics).
            n: Number of users (max 5000).
        """
        with _expected_errors():
            result: list[dict[str, Any]] = to_jsonable(explorer.top_users(by, _rows(n)))
        return result

    @server.tool(annotations=_READ_ONLY)
    def user_profile(author: str, max_chars: int = DEFAULT_MAX_CHARS) -> dict[str, Any]:
        """Profile of one user: activity, habits, interlocutors, latest comments.

        Args:
            author: Exact username (case-sensitive). If unknown, the error
                lists similar usernames.
            max_chars: Maximum characters per comment shown.
        """
        with _expected_errors():
            result: dict[str, Any] = to_jsonable(
                explorer.user(author, _chars(max_chars))
            )
        return result

    @server.tool(annotations=_READ_ONLY)
    def activity(
        by: ActivityPeriod = "hour", author: str | None = None
    ) -> list[dict[str, Any]]:
        """Comments per hour (0-23), weekday, day or month, in local time.

        Args:
            by: hour, weekday, day or month.
            author: Restrict to one user.
        """
        with _expected_errors():
            result: list[dict[str, Any]] = to_jsonable(explorer.activity(by, author))
        return result

    @server.tool(annotations=_READ_ONLY)
    def top_threads(
        by: ThreadRanking = "comments", n: int = 20
    ) -> list[dict[str, Any]]:
        """Rank threads by comments, distinct authors, or recency.

        Args:
            by: comments, authors or recent.
            n: Number of threads (max 5000).
        """
        with _expected_errors():
            result: list[dict[str, Any]] = to_jsonable(
                explorer.top_threads(by, _rows(n))
            )
        return result

    @server.tool(annotations=_READ_ONLY)
    def thread(
        thread_id: str, max_comments: int = 200, max_chars: int = DEFAULT_MAX_CHARS
    ) -> list[dict[str, Any]]:
        """A thread's comments in reading order; depth is the nesting level.

        Args:
            thread_id: Submission ID (with or without 't3_').
            max_comments: Maximum comments returned (max 5000).
            max_chars: Maximum characters per comment.
        """
        with _expected_errors():
            result: list[dict[str, Any]] = to_jsonable(
                explorer.thread(thread_id, _rows(max_comments), _chars(max_chars))
            )
        return result

    @server.tool(annotations=_READ_ONLY)
    def search(
        text: str,
        author: str | None = None,
        n: int = 20,
        max_chars: int = DEFAULT_MAX_CHARS,
    ) -> list[dict[str, Any]]:
        """Comments containing a text (case-insensitive), newest first.

        Args:
            text: Text to find.
            author: Restrict to one user.
            n: Maximum comments (max 5000).
            max_chars: Maximum characters per comment.
        """
        with _expected_errors():
            result: list[dict[str, Any]] = to_jsonable(
                explorer.search(text, _rows(n), author, _chars(max_chars))
            )
        return result

    @server.tool(annotations=_READ_ONLY)
    def interactions(author: str | None = None, n: int = 20) -> list[dict[str, Any]]:
        """Strongest reply relationships: author replied to parent_author N times.

        Args:
            author: Only pairs involving this user.
            n: Number of pairs (max 5000).
        """
        with _expected_errors():
            result: list[dict[str, Any]] = to_jsonable(
                explorer.interactions(author, _rows(n))
            )
        return result

    @server.tool(annotations=_READ_ONLY)
    def run_sql(query: str, limit: int = DEFAULT_SQL_LIMIT) -> list[dict[str, Any]]:
        """Run one read-only DuckDB SELECT over the views listed by schema.

        Args:
            query: A single SELECT (or WITH ... SELECT) statement.
            limit: Maximum rows returned (max 5000).
        """
        with _expected_errors():
            result: list[dict[str, Any]] = to_jsonable(
                explorer.sql(query, _rows(limit))
            )
        return result

    return server
