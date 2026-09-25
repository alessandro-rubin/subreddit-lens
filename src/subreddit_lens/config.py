"""Per-subreddit analysis configuration, loadable from a TOML file.

Example file (subreddit-lens.toml):

    subreddit = "askhistorians"
    timezone = "America/New_York"
    language = "en"
    data_dir = "data"              # relative to this file
    archive_dir = "archives"       # optional, default: data_dir
    output_dir = "output"
    start = 2020-01-01             # optional, inclusive
    end = 2024-12-31               # optional, inclusive
    exclude_authors = ["[deleted]", "AutoModerator", "RemindMeBot"]

Archive and Parquet file names follow the convention used by the
per-subreddit Pushshift/Arctic Shift dumps: '<subreddit>_comments.zst' and
'<subreddit>_submissions.zst' in archive_dir, which defaults to data_dir.
The Parquet files are written to data_dir.
"""

import re
import tomllib
from collections.abc import Callable
from dataclasses import dataclass, field, fields
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from subreddit_lens.constants import DEFAULT_EXCLUDED_AUTHORS

# Subreddit names: 2-21 characters, letters, digits and underscores
# (3 is the minimum for new subreddits, but some old ones are shorter).
_SUBREDDIT_PATTERN = re.compile(r"^[A-Za-z0-9_]{2,21}$")


@dataclass(frozen=True)
class Config:
    """Settings for analysing one subreddit.

    Attributes:
        subreddit: Subreddit name without the 'r/' prefix.
        data_dir: Directory with the Parquet files (and the input archives,
            unless archive_dir is set).
        output_dir: Directory for figures, graphs and exports.
        archive_dir: Directory with the input zstd archives, or None to read
            them from data_dir. Set it to read archives shared with other
            tools without writing next to them.
        timezone: IANA timezone used for time-of-day analyses.
        language: ISO 639-1 code of the subreddit's main language.
        start: First day to include (UTC), or None for no lower bound.
        end: Last day to include (UTC), or None for no upper bound.
        exclude_authors: Usernames left out of per-user analyses.
    """

    subreddit: str
    data_dir: Path = Path("data")
    output_dir: Path = Path("output")
    timezone: str = "UTC"
    language: str = "en"
    start: date | None = None
    end: date | None = None
    exclude_authors: frozenset[str] = field(default=DEFAULT_EXCLUDED_AUTHORS)
    archive_dir: Path | None = None

    def __post_init__(self) -> None:
        """Validate the settings.

        Raises:
            ValueError: If a setting is invalid.
        """
        if not _SUBREDDIT_PATTERN.fullmatch(self.subreddit):
            raise ValueError(f"Invalid subreddit name: {self.subreddit!r}")
        try:
            ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"Unknown timezone: {self.timezone!r}") from exc
        if not re.fullmatch(r"[a-z]{2}", self.language):
            raise ValueError(f"Language must be an ISO 639-1 code: {self.language!r}")
        if self.start and self.end and self.start > self.end:
            raise ValueError(f"start ({self.start}) is after end ({self.end})")

    def _archive(self, kind: str) -> Path:
        directory = self.data_dir if self.archive_dir is None else self.archive_dir
        return directory / f"{self.subreddit}_{kind}.zst"

    @property
    def comments_archive(self) -> Path:
        """Path of the comments zstd archive (in archive_dir, or data_dir)."""
        return self._archive("comments")

    @property
    def submissions_archive(self) -> Path:
        """Path of the submissions zstd archive (in archive_dir, or data_dir)."""
        return self._archive("submissions")

    @property
    def comments_parquet(self) -> Path:
        """Path of the comments Parquet file."""
        return self.data_dir / f"{self.subreddit}_comments.parquet"

    @property
    def submissions_parquet(self) -> Path:
        """Path of the submissions Parquet file."""
        return self.data_dir / f"{self.subreddit}_submissions.parquet"

    @property
    def users_graph(self) -> Path:
        """Path of the user interaction graph (GraphML)."""
        return self.output_dir / f"{self.subreddit}_users.graphml"

    @property
    def user_metrics_file(self) -> Path:
        """Path of the per-user metrics table (CSV)."""
        return self.output_dir / f"{self.subreddit}_user_metrics.csv"

    @property
    def habits_file(self) -> Path:
        """Path of the per-user hourly activity densities (Parquet)."""
        return self.output_dir / f"{self.subreddit}_habits.parquet"

    @property
    def chains_file(self) -> Path:
        """Path of the conversation chains export (JSONL)."""
        return self.output_dir / f"{self.subreddit}_threads.jsonl"

    @property
    def pairs_file(self) -> Path:
        """Path of the prompt/response pairs export (JSONL)."""
        return self.output_dir / f"{self.subreddit}_pairs.jsonl"

    def date_filter(self) -> Callable[[dict[str, Any]], bool] | None:
        """Return a record filter for the configured date range.

        The filter reads 'created_utc' from raw archive records, so it can be
        passed as the condition of subreddit_lens.io.ingest_archive().

        Returns:
            A predicate on records, or None when no range is configured.
        """
        if self.start is None and self.end is None:
            return None
        lower = (
            datetime.combine(self.start, time.min, UTC).timestamp()
            if self.start
            else float("-inf")
        )
        upper = (
            datetime.combine(self.end + timedelta(days=1), time.min, UTC).timestamp()
            if self.end
            else float("inf")
        )

        def in_range(record: dict[str, Any]) -> bool:
            try:
                ts = float(record["created_utc"])
            except (KeyError, TypeError, ValueError):
                return False
            return lower <= ts < upper

        return in_range


def _as_date(value: Any, key: str) -> date | None:
    if value is None or isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value)
    raise ValueError(f"{key} must be a date (YYYY-MM-DD), got {value!r}")


# Expected TOML value types; dates are checked by _as_date().
_TOML_TYPES: dict[str, type] = {
    "subreddit": str,
    "data_dir": str,
    "output_dir": str,
    "archive_dir": str,
    "timezone": str,
    "language": str,
    "exclude_authors": list,
}


def load_config(path: str | Path) -> Config:
    """Load a Config from a TOML file.

    Relative data_dir, output_dir and archive_dir are resolved against the
    directory that contains the file, so a config works regardless of the
    current working directory. exclude_authors, when given, replaces the
    default list.

    Args:
        path: Path to the TOML file.

    Returns:
        The validated configuration.

    Raises:
        FileNotFoundError: If path does not exist.
        ValueError: If the file has unknown keys or invalid values.
        tomllib.TOMLDecodeError: If the file is not valid TOML.
    """
    path = Path(path)
    with path.open("rb") as f:
        raw: dict[str, Any] = tomllib.load(f)

    known = {f.name for f in fields(Config)}
    unknown = sorted(set(raw) - known)
    if unknown:
        raise ValueError(f"Unknown keys in {path}: {unknown}")
    for key, expected in _TOML_TYPES.items():
        if key in raw and not isinstance(raw[key], expected):
            raise ValueError(
                f"{key} in {path} must be a {expected.__name__}, got {raw[key]!r}"
            )
    if not all(isinstance(a, str) for a in raw.get("exclude_authors", [])):
        raise ValueError(f"exclude_authors in {path} must be a list of strings")

    base = path.parent
    kwargs: dict[str, Any] = dict(raw)
    for key in ("data_dir", "output_dir"):
        if key in kwargs:
            kwargs[key] = (base / kwargs[key]).resolve()
        else:
            kwargs[key] = (base / getattr(Config, key)).resolve()
    if "archive_dir" in kwargs:
        kwargs["archive_dir"] = (base / kwargs["archive_dir"]).resolve()
    for key in ("start", "end"):
        if key in kwargs:
            kwargs[key] = _as_date(kwargs[key], key)
    if "exclude_authors" in kwargs:
        kwargs["exclude_authors"] = frozenset(kwargs["exclude_authors"])
    return Config(**kwargs)
