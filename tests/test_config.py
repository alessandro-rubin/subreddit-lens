"""Tests for subreddit_lens.config."""

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from subreddit_lens.config import Config, load_config
from subreddit_lens.constants import DEFAULT_EXCLUDED_AUTHORS


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "conf" / "subreddit-lens.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


class TestLoadConfig:
    def test_full_file(self, tmp_path: Path) -> None:
        path = write(
            tmp_path,
            """
            subreddit = "demo"
            timezone = "Europe/Rome"
            language = "it"
            data_dir = "../data"
            archive_dir = "../raw"
            output_dir = "out"
            start = 2020-01-01
            end = "2020-12-31"
            exclude_authors = ["[deleted]", "RemindMeBot"]
            """,
        )
        config = load_config(path)
        assert config.subreddit == "demo"
        assert config.data_dir == (tmp_path / "data").resolve()
        assert config.output_dir == (tmp_path / "conf" / "out").resolve()
        assert config.start == date(2020, 1, 1)
        assert config.end == date(2020, 12, 31)
        assert config.exclude_authors == {"[deleted]", "RemindMeBot"}
        # Archives are read from archive_dir, Parquet files go to data_dir.
        raw = (tmp_path / "raw").resolve()
        assert config.comments_archive == raw / "demo_comments.zst"
        assert config.submissions_archive == raw / "demo_submissions.zst"
        assert config.comments_parquet == config.data_dir / "demo_comments.parquet"
        assert config.submissions_parquet.name == "demo_submissions.parquet"

    def test_defaults(self, tmp_path: Path) -> None:
        config = load_config(write(tmp_path, 'subreddit = "AskItaly"'))
        assert config.timezone == "UTC"
        assert config.exclude_authors == DEFAULT_EXCLUDED_AUTHORS
        assert config.data_dir == (tmp_path / "conf" / "data").resolve()
        assert config.archive_dir is None
        assert config.comments_archive.parent == config.data_dir
        assert config.date_filter() is None

    @pytest.mark.parametrize(
        "text",
        [
            "subreddit = 123",
            'subreddit = "demo"\ndata_dir = 5',
            'subreddit = "demo"\narchive_dir = ["raw"]',
            'subreddit = "demo"\nexclude_authors = "AutoModerator"',
            'subreddit = "demo"\nexclude_authors = [1, 2]',
        ],
    )
    def test_wrong_value_types(self, tmp_path: Path, text: str) -> None:
        # Regression: these raised TypeError, which the CLI does not catch.
        with pytest.raises(ValueError):
            load_config(write(tmp_path, text))

    def test_unknown_key(self, tmp_path: Path) -> None:
        path = write(tmp_path, 'subreddit = "demo"\ntimzone = "Europe/Rome"')
        with pytest.raises(ValueError, match="timzone"):
            load_config(path)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"subreddit": "r/demo"},
        {"subreddit": "x"},
        {"subreddit": "demo", "timezone": "Europe/Atlantis"},
        {"subreddit": "demo", "language": "italian"},
        {"subreddit": "demo", "start": date(2021, 1, 1), "end": date(2020, 1, 1)},
    ],
)
def test_invalid_settings(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        Config(**kwargs)  # type: ignore[arg-type]


def test_date_filter_bounds_are_inclusive_utc_days() -> None:
    config = Config("demo", start=date(2024, 7, 1), end=date(2024, 7, 1))
    in_range = config.date_filter()
    assert in_range is not None

    def at(ts: str) -> dict[str, object]:
        return {"created_utc": pd.Timestamp(ts, tz="UTC").timestamp()}

    assert in_range(at("2024-07-01 00:00"))
    assert in_range(at("2024-07-01 23:59:59"))
    assert not in_range(at("2024-06-30 23:59:59"))
    assert not in_range(at("2024-07-02 00:00"))
    noon = int(pd.Timestamp("2024-07-01 12:00", tz="UTC").timestamp())
    assert in_range({"created_utc": str(noon)})  # string timestamps in old dumps
    assert not in_range({"id": "no timestamp"})


def test_open_ended_range() -> None:
    in_range = Config("demo", start=date(2024, 1, 1)).date_filter()
    assert in_range is not None
    assert in_range({"created_utc": 4_000_000_000})
    assert not in_range({"created_utc": 0})
