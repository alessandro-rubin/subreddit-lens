"""Per-subreddit analysis configuration, loadable from a TOML file.

Example file (subreddit-lens.toml):

    subreddit = "litigi"
    timezone = "Europe/Rome"
    language = "it"
    data_dir = "../../data"        # relative to this file
    output_dir = "../../output"
    start = 2020-01-01             # optional, inclusive
    end = 2024-12-31               # optional, inclusive
    exclude_authors = ["[deleted]", "AutoModerator", "RemindMeBot"]

Archive and Parquet file names follow the convention used by the
per-subreddit Pushshift/Arctic Shift dumps: '<subreddit>_comments.zst' and
'<subreddit>_submissions.zst' in data_dir.
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
        data_dir: Directory with the input archives and Parquet files.
        output_dir: Directory for figures, graphs and exports.
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

    @property
    def comments_archive(self) -> Path:
        """Path of the comments zstd archive."""
        return self.data_dir / f"{self.subreddit}_comments.zst"

    @property
    def submissions_archive(self) -> Path:
        """Path of the submissions zstd archive."""
        return self.data_dir / f"{self.subreddit}_submissions.zst"

    @property
    def comments_parquet(self) -> Path:
        """Path of the comments Parquet file."""
        return self.data_dir / f"{self.subreddit}_comments.parquet"

    @property
    def submissions_parquet(self) -> Path:
        """Path of the submissions Parquet file."""
        return self.data_dir / f"{self.subreddit}_submissions.parquet"

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


def load_config(path: str | Path) -> Config:
    """Load a Config from a TOML file.

    Relative data_dir and output_dir are resolved against the directory that
    contains the file, so a config works regardless of the current working
    directory. exclude_authors, when given, replaces the default list.

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

    base = path.parent
    kwargs: dict[str, Any] = dict(raw)
    for key in ("data_dir", "output_dir"):
        if key in kwargs:
            kwargs[key] = (base / kwargs[key]).resolve()
        else:
            kwargs[key] = (base / getattr(Config, key)).resolve()
    for key in ("start", "end"):
        if key in kwargs:
            kwargs[key] = _as_date(kwargs[key], key)
    if "exclude_authors" in kwargs:
        kwargs["exclude_authors"] = frozenset(kwargs["exclude_authors"])
    return Config(**kwargs)
