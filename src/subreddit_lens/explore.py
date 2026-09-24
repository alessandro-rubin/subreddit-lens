"""Interactive exploration and analytics over a subreddit, backed by DuckDB.

The Explorer opens the Parquet files produced by the ingest step as SQL views
and answers common questions with ready-made queries. Every table result is a
pandas DataFrame; profile-style results are plain dicts. Both convert to JSON
with to_jsonable(), which is what the CLI (--json) and the MCP server return.

Views (queryable with Explorer.sql()):

    comments          one row per comment, plus thread_id and created_at
                      (local time in the configured timezone)
    submissions       one row per submission (only if ingested)
    replies           one row per comment whose parent author is known:
                      author replied to parent_author (excluded authors
                      removed)
    users             one row per author: activity counts, first/last seen,
                      replies sent/received (excluded authors removed)
    threads           one row per thread: title, submitter, comments, authors
    user_metrics      network metrics from the metrics step (only if computed)
    excluded_authors  usernames left out of per-user analyses

Example:
    >>> ex = Explorer.from_config("subreddit-lens.toml")
    >>> ex.summary()["n_comments"]
    123456
    >>> ex.top_users(by="replies_received", n=5)
    >>> ex.sql("SELECT author, count(*) FROM comments GROUP BY 1 ORDER BY 2 DESC")
"""

from __future__ import annotations

import html
import json
import math
import threading
from collections.abc import Mapping
from datetime import date, datetime
from pathlib import Path
from typing import Any, Literal

import duckdb
import numpy as np
import pandas as pd

from subreddit_lens.config import Config, load_config

UserRanking = Literal[
    "comments",
    "submissions",
    "threads",
    "score",
    "replies_received",
    "replies_sent",
    "pagerank",
]
ActivityPeriod = Literal["hour", "weekday", "day", "month"]
ThreadRanking = Literal["comments", "authors", "recent"]

DEFAULT_MAX_CHARS = 300
DEFAULT_SQL_LIMIT = 1000

_USER_COLUMNS: dict[str, str] = {
    "comments": "n_comments",
    "submissions": "n_submissions",
    "threads": "n_threads",
    "score": "total_score",
    "replies_received": "replies_received",
    "replies_sent": "replies_sent",
}
_THREAD_ORDER: dict[str, str] = {
    "comments": "n_comments DESC",
    "authors": "n_authors DESC",
    "recent": "last_comment DESC",
}
_WEEKDAYS = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]


class QueryError(ValueError):
    """Raised for invalid or disallowed queries and unknown names."""


def _quote(value: str) -> str:
    """Quote a string literal for DuckDB SQL."""
    return "'" + value.replace("'", "''") + "'"


def _ident(name: str) -> str:
    """Quote an identifier for DuckDB SQL."""
    return '"' + name.replace('"', '""') + '"'


def _jsonable_scalar(value: Any) -> Any:
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, np.generic):
        return _jsonable_scalar(value.item())
    if isinstance(value, pd.Timestamp | datetime | date):
        return value.isoformat()
    return value


def _decode_text(df: pd.DataFrame) -> pd.DataFrame:
    """Decode HTML entities in text columns of query results.

    Reddit stores bodies HTML-escaped ('&gt;', '&amp;'); decoding them lets
    people and AI assistants read the text as written.
    """
    for column in ("body", "title", "selftext"):
        if column in df.columns:
            df[column] = df[column].map(
                lambda v: html.unescape(v) if isinstance(v, str) else v
            )
    return df


def to_jsonable(obj: Any) -> Any:
    """Convert Explorer results to plain JSON-serialisable Python objects.

    DataFrames become lists of records; timestamps become ISO 8601 strings;
    NaN and pandas missing values become None.

    Args:
        obj: A DataFrame, Series, dict, list or scalar.

    Returns:
        An object that json.dumps() accepts.
    """
    if isinstance(obj, pd.DataFrame):
        return [
            {str(k): _jsonable_scalar(v) for k, v in row.items()}
            for row in obj.to_dict(orient="records")
        ]
    if isinstance(obj, pd.Series):
        return to_jsonable(obj.to_dict())
    if isinstance(obj, Mapping):
        return {str(k): to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, list | tuple):
        return [to_jsonable(v) for v in obj]
    return _jsonable_scalar(obj)


def to_json(obj: Any, indent: int | None = 2) -> str:
    """Serialise an Explorer result to a JSON string (UTF-8, not escaped)."""
    return json.dumps(to_jsonable(obj), ensure_ascii=False, indent=indent)


class Explorer:
    """Query a subreddit's ingested data with ready-made analyses and SQL.

    The connection is sandboxed: queries can read only files inside the data
    and output directories, cannot write files, install extensions or change
    settings, and Explorer.sql() accepts only SELECT statements. This makes it
    safe to expose to an AI assistant.

    Args:
        config: Pipeline configuration. The comments Parquet file must exist
            (run the ingest step first); submissions and user metrics are
            used when present.

    Raises:
        FileNotFoundError: If the comments Parquet file does not exist.
    """

    def __init__(self, config: Config) -> None:
        self.config = config
        if not config.comments_parquet.exists():
            raise FileNotFoundError(
                f"{config.comments_parquet} not found. Run the ingest step first."
            )
        self.has_submissions = config.submissions_parquet.exists()
        self.has_metrics = config.user_metrics_file.exists()
        self._lock = threading.Lock()
        self._con = duckdb.connect()
        self._create_views()
        self._sandbox()

    @classmethod
    def from_config(cls, path: str | Path) -> Explorer:
        """Open the data described by a TOML configuration file."""
        return cls(load_config(path))

    def close(self) -> None:
        """Close the DuckDB connection."""
        self._con.close()

    def __enter__(self) -> Explorer:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- setup ---------------------------------------------------------------

    def _columns(self, source: str) -> list[str]:
        rows = self._con.execute(f"DESCRIBE SELECT * FROM {source}").fetchall()
        return [str(r[0]) for r in rows]

    def _create_views(self) -> None:
        con = self._con
        tz = _quote(self.config.timezone)
        excluded = sorted(self.config.exclude_authors)

        con.execute("CREATE TABLE excluded_authors (author VARCHAR)")
        if excluded:
            con.executemany(
                "INSERT INTO excluded_authors VALUES (?)", [[a] for a in excluded]
            )

        source = f"read_parquet({_quote(str(self.config.comments_parquet))})"
        derived = {"thread_id", "created_at"}
        columns = [c for c in self._columns(source) if c not in derived]
        self._comment_columns = set(columns)
        select = ", ".join(_ident(c) for c in columns)
        con.execute(
            f"""
            CREATE VIEW comments AS
            SELECT {select},
                   regexp_replace(link_id, '^t3_', '') AS thread_id,
                   timezone({tz}, to_timestamp(created_utc)) AS created_at
            FROM {source}
            """
        )

        if self.has_submissions:
            source = f"read_parquet({_quote(str(self.config.submissions_parquet))})"
            columns = [c for c in self._columns(source) if c != "created_at"]
            select = ", ".join(_ident(c) for c in columns)
            con.execute(
                f"""
                CREATE VIEW submissions AS
                SELECT {select},
                       timezone({tz}, to_timestamp(created_utc)) AS created_at
                FROM {source}
                """
            )
            op_source = (
                "SELECT id, any_value(author) AS author FROM submissions GROUP BY id"
            )
        elif "is_submitter" in self._comment_columns:
            op_source = (
                "SELECT thread_id AS id, any_value(author) AS author "
                "FROM comments WHERE is_submitter GROUP BY thread_id"
            )
        else:
            op_source = "SELECT NULL::VARCHAR AS id, NULL::VARCHAR AS author LIMIT 0"

        con.execute(
            f"""
            CREATE VIEW replies AS
            WITH parents AS (
                SELECT id, any_value(author) AS author FROM comments GROUP BY id
            ),
            ops AS ({op_source}),
            resolved AS (
                SELECT c.id AS comment_id, c.thread_id, c.author, c.created_at,
                       CASE WHEN c.parent_id LIKE 't1_%' THEN 'comment'
                            ELSE 'submission' END AS parent_kind,
                       CASE WHEN c.parent_id LIKE 't1_%' THEN p.author
                            ELSE o.author END AS parent_author
                FROM comments c
                LEFT JOIN parents p ON c.parent_id = 't1_' || p.id
                LEFT JOIN ops o ON c.parent_id = 't3_' || o.id
            )
            SELECT * FROM resolved
            WHERE parent_author IS NOT NULL
              AND author NOT IN (SELECT author FROM excluded_authors)
              AND parent_author NOT IN (SELECT author FROM excluded_authors)
            """
        )

        submissions_join = (
            """
            FULL OUTER JOIN (
                SELECT author, count(*) AS n_submissions FROM submissions
                GROUP BY author
            ) s USING (author)
            """
            if self.has_submissions
            else "LEFT JOIN (SELECT NULL::VARCHAR AS author, 0 AS n_submissions "
            "LIMIT 0) s USING (author)"
        )
        con.execute(
            f"""
            CREATE VIEW users AS
            WITH c AS (
                SELECT author, count(*) AS n_comments,
                       count(DISTINCT thread_id) AS n_threads,
                       sum(score) AS total_score,
                       min(created_at) AS first_seen, max(created_at) AS last_seen
                FROM comments GROUP BY author
            ),
            received AS (
                SELECT parent_author AS author, count(*) AS replies_received
                FROM replies WHERE author <> parent_author GROUP BY 1
            ),
            sent AS (
                SELECT author, count(*) AS replies_sent
                FROM replies WHERE author <> parent_author GROUP BY 1
            ),
            base AS (
                SELECT author,
                       coalesce(n_comments, 0) AS n_comments,
                       coalesce(n_submissions, 0) AS n_submissions,
                       coalesce(n_threads, 0) AS n_threads,
                       coalesce(total_score, 0) AS total_score,
                       first_seen, last_seen
                FROM c {submissions_join}
            )
            SELECT base.*,
                   coalesce(received.replies_received, 0) AS replies_received,
                   coalesce(sent.replies_sent, 0) AS replies_sent
            FROM base
            LEFT JOIN received USING (author)
            LEFT JOIN sent USING (author)
            WHERE author IS NOT NULL
              AND author NOT IN (SELECT author FROM excluded_authors)
            """
        )

        if self.has_submissions:
            title, submitter = "s.title", "s.author"
            thread_join = "LEFT JOIN submissions s ON s.id = c.thread_id"
        else:
            title, submitter = "NULL::VARCHAR", "o.author"
            thread_join = f"LEFT JOIN ({op_source}) o ON o.id = c.thread_id"
        con.execute(
            f"""
            CREATE VIEW threads AS
            SELECT c.thread_id,
                   any_value({title}) AS title,
                   any_value({submitter}) AS submitter,
                   count(*) AS n_comments,
                   count(DISTINCT c.author) AS n_authors,
                   min(c.created_at) AS first_comment,
                   max(c.created_at) AS last_comment
            FROM comments c {thread_join}
            GROUP BY c.thread_id
            """
        )

        if self.has_metrics:
            path = _quote(str(self.config.user_metrics_file))
            con.execute(
                f"CREATE VIEW user_metrics AS SELECT * FROM read_csv_auto({path})"
            )

    def _sandbox(self) -> None:
        """Restrict file access to the data and output directories and lock it."""
        dirs = {self.config.data_dir.resolve(), self.config.output_dir.resolve()}
        allowed = ", ".join(_quote(str(d) + "/") for d in sorted(dirs))
        self._con.execute(f"SET allowed_directories = [{allowed}]")
        self._con.execute("SET enable_external_access = false")
        self._con.execute("SET lock_configuration = true")

    # -- low level -----------------------------------------------------------

    def _df(self, query: str, params: Mapping[str, Any] | None = None) -> pd.DataFrame:
        with self._lock:
            return _decode_text(self._con.execute(query, dict(params or {})).df())

    def sql(self, query: str, limit: int | None = DEFAULT_SQL_LIMIT) -> pd.DataFrame:
        """Run a read-only SQL query against the views and return a DataFrame.

        Only a single SELECT statement (including WITH ... SELECT) is
        accepted. See schema() for the available views and columns.

        Args:
            query: DuckDB SQL.
            limit: Maximum number of rows returned; None for no limit.

        Returns:
            Query result.

        Raises:
            QueryError: If the query is not a single SELECT statement, or
                fails.
        """
        with self._lock:
            try:
                statements = self._con.extract_statements(query)
            except duckdb.Error as exc:
                raise QueryError(f"Invalid SQL: {exc}") from exc
            if len(statements) != 1:
                raise QueryError("Pass exactly one SQL statement.")
            if statements[0].type != duckdb.StatementType.SELECT:
                raise QueryError("Only SELECT queries are allowed.")
            try:
                relation = self._con.sql(query)
                if limit is not None:
                    relation = relation.limit(limit)
                return _decode_text(relation.df())
            except duckdb.Error as exc:
                raise QueryError(str(exc)) from exc

    def schema(self) -> dict[str, list[dict[str, str]]]:
        """Describe the queryable views: name -> list of {column, type}."""
        views = self._df(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'main' ORDER BY table_name"
        )["table_name"]
        return {
            str(view): [
                {"column": str(r[0]), "type": str(r[1])}
                for r in self._con.execute(f"DESCRIBE {_ident(str(view))}").fetchall()
            ]
            for view in views
        }

    # -- ready-made analyses ---------------------------------------------------

    def summary(self) -> dict[str, Any]:
        """Return an overview of the dataset: size, time span, busiest times.

        Returns:
            Dict with the subreddit, timezone, counts of comments,
            submissions, authors and threads, first and last comment time,
            average comments per day, busiest hour and weekday, the top five
            commenters and which optional data is available.
        """
        totals = self._df(
            """
            SELECT count(*) AS n_comments,
                   count(DISTINCT author) AS n_authors,
                   count(DISTINCT thread_id) AS n_threads,
                   min(created_at) AS first_comment,
                   max(created_at) AS last_comment
            FROM comments
            """
        ).iloc[0]
        span_days = 0.0
        if pd.notna(totals["first_comment"]):
            span = pd.Timestamp(totals["last_comment"]) - pd.Timestamp(
                totals["first_comment"]
            )
            span_days = max(span.total_seconds() / 86400, 1.0)
        hours = self.activity("hour")
        weekdays = self.activity("weekday")
        n_comments = int(totals["n_comments"])
        return {
            "subreddit": self.config.subreddit,
            "timezone": self.config.timezone,
            "n_comments": n_comments,
            "n_submissions": (
                int(self._df("SELECT count(*) AS n FROM submissions")["n"].iloc[0])
                if self.has_submissions
                else None
            ),
            "n_authors": int(totals["n_authors"]),
            "n_threads": int(totals["n_threads"]),
            "first_comment": totals["first_comment"],
            "last_comment": totals["last_comment"],
            "comments_per_day": round(n_comments / span_days, 2) if span_days else 0,
            "busiest_hour": (
                int(hours["hour"].iloc[int(hours["comments"].to_numpy().argmax())])
                if n_comments
                else None
            ),
            "busiest_weekday": (
                str(
                    weekdays["weekday"].iloc[
                        int(weekdays["comments"].to_numpy().argmax())
                    ]
                )
                if n_comments
                else None
            ),
            "top_commenters": self.top_users("comments", n=5)[["author", "n_comments"]],
            "has_submissions": self.has_submissions,
            "has_network_metrics": self.has_metrics,
            "excluded_authors": sorted(self.config.exclude_authors),
        }

    def top_users(self, by: UserRanking = "comments", n: int = 20) -> pd.DataFrame:
        """Rank users by activity or influence.

        Args:
            by: 'comments', 'submissions', 'threads' (distinct threads
                commented in), 'score' (sum of comment scores),
                'replies_received', 'replies_sent', or 'pagerank' (needs the
                metrics step).
            n: Number of users.

        Returns:
            One row per user from the users view (plus network metrics for
            'pagerank').

        Raises:
            QueryError: If the ranking is unknown or its data is missing.
        """
        if by == "pagerank":
            if not self.has_metrics:
                raise QueryError(
                    "PageRank needs network metrics: run the network and metrics "
                    "steps first."
                )
            return self._df(
                """
                SELECT u.*, m.pagerank, m.hindex, m.community
                FROM user_metrics m JOIN users u USING (author)
                ORDER BY m.pagerank DESC LIMIT $n
                """,
                {"n": n},
            )
        if by not in _USER_COLUMNS:
            choices = sorted([*_USER_COLUMNS, "pagerank"])
            raise QueryError(f"Unknown ranking {by!r}; use one of {choices}")
        column = _USER_COLUMNS[by]
        return self._df(
            f"SELECT * FROM users ORDER BY {column} DESC, author LIMIT $n", {"n": n}
        )

    def _require_user(self, author: str) -> None:
        found = self._df(
            "SELECT count(*) AS n FROM comments WHERE author = $a", {"a": author}
        )["n"].iloc[0]
        if found:
            return
        similar = self._df(
            """
            SELECT author FROM users
            ORDER BY jaro_winkler_similarity(lower(author), lower($a)) DESC LIMIT 5
            """,
            {"a": author},
        )["author"].tolist()
        raise QueryError(f"No comments by {author!r}. Similar usernames: {similar}")

    def activity(
        self, by: ActivityPeriod = "hour", author: str | None = None
    ) -> pd.DataFrame:
        """Count comments per period in the configured timezone.

        Args:
            by: 'hour' (0-23), 'weekday' (Monday-Sunday), 'day' or 'month'.
                Hours and weekdays include periods with no comments.
            author: Restrict to one user.

        Returns:
            Two columns: the period and 'comments'.

        Raises:
            QueryError: If the period is unknown or the author has no
                comments.
        """
        if author is not None:
            self._require_user(author)
        where = "WHERE author = $a" if author is not None else ""
        params = {"a": author} if author is not None else {}
        if by == "hour":
            return self._df(
                f"""
                SELECT h.hour, coalesce(c.comments, 0) AS comments
                FROM range(24) h(hour)
                LEFT JOIN (SELECT hour(created_at) AS hour, count(*) AS comments
                           FROM comments {where} GROUP BY 1) c USING (hour)
                ORDER BY h.hour
                """,
                params,
            )
        if by == "weekday":
            counts = self._df(
                f"""
                SELECT isodow(created_at) AS day, count(*) AS comments
                FROM comments {where} GROUP BY 1
                """,
                params,
            ).set_index("day")["comments"]
            return pd.DataFrame(
                {
                    "weekday": _WEEKDAYS,
                    "comments": [int(counts.get(i + 1, 0)) for i in range(7)],
                }
            )
        if by in ("day", "month"):
            return self._df(
                f"""
                SELECT date_trunc('{by}', created_at)::DATE AS {by},
                       count(*) AS comments
                FROM comments {where} GROUP BY 1 ORDER BY 1
                """,
                params,
            )
        raise QueryError(f"Unknown period {by!r}; use hour, weekday, day or month")

    def user(self, author: str, max_chars: int = DEFAULT_MAX_CHARS) -> dict[str, Any]:
        """Return a profile of one user.

        Args:
            author: Username (case-sensitive).
            max_chars: Maximum characters of each recent comment.

        Returns:
            Dict with the users-view row, network metrics (if computed),
            busiest hours and weekdays, the users they reply to most, the
            users who reply to them most, and their five latest comments.

        Raises:
            QueryError: If the user has no comments (with similar names).
        """
        self._require_user(author)
        params = {"a": author}
        row = self._df("SELECT * FROM users WHERE author = $a", params)
        profile: dict[str, Any] = (
            {str(k): v for k, v in row.iloc[0].items()}
            if len(row)
            else {"author": author}
        )
        if self.has_metrics:
            metrics = self._df("SELECT * FROM user_metrics WHERE author = $a", params)
            profile["network"] = metrics.iloc[0].to_dict() if len(metrics) else None
        hours = self.activity("hour", author)
        profile["busiest_hours"] = (
            hours.sort_values("comments", ascending=False).head(3)["hour"].tolist()
        )
        profile["weekdays"] = self.activity("weekday", author)
        profile["replies_to"] = self._df(
            """
            SELECT parent_author AS author, count(*) AS replies FROM replies
            WHERE author = $a AND parent_author <> $a
            GROUP BY 1 ORDER BY 2 DESC, 1 LIMIT 5
            """,
            params,
        )
        profile["replied_by"] = self._df(
            """
            SELECT author, count(*) AS replies FROM replies
            WHERE parent_author = $a AND author <> $a
            GROUP BY 1 ORDER BY 2 DESC, 1 LIMIT 5
            """,
            params,
        )
        profile["recent_comments"] = self._df(
            """
            SELECT id, thread_id, created_at, score, left(body, $m) AS body
            FROM comments WHERE author = $a
            ORDER BY created_utc DESC LIMIT 5
            """,
            {"a": author, "m": max_chars},
        )
        return profile

    def top_threads(self, by: ThreadRanking = "comments", n: int = 20) -> pd.DataFrame:
        """Rank threads by number of comments, distinct authors, or recency.

        Args:
            by: 'comments', 'authors' or 'recent' (latest comment first).
            n: Number of threads.

        Returns:
            Rows of the threads view.

        Raises:
            QueryError: If the ranking is unknown.
        """
        if by not in _THREAD_ORDER:
            raise QueryError(f"Unknown ranking {by!r}; use {sorted(_THREAD_ORDER)}")
        return self._df(
            f"SELECT * FROM threads ORDER BY {_THREAD_ORDER[by]}, thread_id LIMIT $n",
            {"n": n},
        )

    def thread(
        self,
        thread_id: str,
        max_comments: int = 500,
        max_chars: int = DEFAULT_MAX_CHARS,
    ) -> pd.DataFrame:
        """Return a thread's comments in reading order, with their depth.

        Comments are ordered depth-first, replies after their parent and
        siblings by time. Comments whose parent is missing from the data are
        shown as top-level (depth 1).

        Args:
            thread_id: Submission ID, with or without the 't3_' prefix.
            max_comments: Maximum number of comments returned.
            max_chars: Maximum characters of each comment body.

        Returns:
            Columns depth, id, parent_id, author, created_at, score, body.

        Raises:
            QueryError: If the thread has no comments.
        """
        tid = thread_id.removeprefix("t3_")
        result = self._df(
            """
            WITH RECURSIVE
            t AS (SELECT * FROM comments WHERE thread_id = $tid),
            tree AS (
                SELECT id, parent_id, author, created_at, score, body,
                       1 AS depth,
                       [lpad(created_utc::VARCHAR, 12, '0') || id] AS path
                FROM t
                WHERE parent_id = 't3_' || $tid
                   OR (parent_id LIKE 't1_%'
                       AND substr(parent_id, 4) NOT IN (SELECT id FROM t))
                UNION ALL
                SELECT c.id, c.parent_id, c.author, c.created_at, c.score, c.body,
                       tree.depth + 1,
                       list_append(tree.path,
                                   lpad(c.created_utc::VARCHAR, 12, '0') || c.id)
                FROM t c JOIN tree ON c.parent_id = 't1_' || tree.id
            )
            SELECT depth, id, parent_id, author, created_at, score,
                   left(body, $m) AS body
            FROM tree ORDER BY path LIMIT $n
            """,
            {"tid": tid, "m": max_chars, "n": max_comments},
        )
        if result.empty:
            raise QueryError(f"No comments in thread {thread_id!r}")
        return result

    def search(
        self,
        text: str,
        n: int = 20,
        author: str | None = None,
        max_chars: int = DEFAULT_MAX_CHARS,
    ) -> pd.DataFrame:
        """Find comments containing a text (case-insensitive substring).

        Args:
            text: Text to look for.
            n: Maximum number of comments, newest first.
            author: Restrict to one user.
            max_chars: Maximum characters of each comment body.

        Returns:
            Columns id, thread_id, author, created_at, score, body.
        """
        where = "AND author = $a" if author is not None else ""
        params: dict[str, Any] = {"q": text, "n": n, "m": max_chars}
        if author is not None:
            params["a"] = author
        return self._df(
            f"""
            SELECT id, thread_id, author, created_at, score, left(body, $m) AS body
            FROM comments
            WHERE contains(lower(body), lower($q)) {where}
            ORDER BY created_utc DESC LIMIT $n
            """,
            params,
        )

    def interactions(self, author: str | None = None, n: int = 20) -> pd.DataFrame:
        """Return the strongest reply relationships between users.

        Args:
            author: If given, only pairs involving this user.
            n: Number of pairs.

        Returns:
            Columns author, parent_author (the user replied to) and replies,
            strongest first. Self-replies are excluded.

        Raises:
            QueryError: If the author has no comments.
        """
        if author is not None:
            self._require_user(author)
        where = "AND (author = $a OR parent_author = $a)" if author is not None else ""
        params: dict[str, Any] = {"n": n}
        if author is not None:
            params["a"] = author
        return self._df(
            f"""
            SELECT author, parent_author, count(*) AS replies FROM replies
            WHERE author <> parent_author {where}
            GROUP BY 1, 2 ORDER BY 3 DESC, 1, 2 LIMIT $n
            """,
            params,
        )
