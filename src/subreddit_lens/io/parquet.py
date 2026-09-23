"""Readers for Parquet files produced by the ingestion pipeline."""

from pathlib import Path

import pandas as pd

from subreddit_lens.io.schema import normalize


def _read(parquet_path: str | Path) -> pd.DataFrame:
    parquet_path = Path(parquet_path)
    if not parquet_path.exists():
        raise FileNotFoundError(f"Parquet file not found: {parquet_path}")
    return pd.read_parquet(parquet_path)


def load_comments(parquet_path: str | Path) -> pd.DataFrame:
    """Load a Reddit comments Parquet file and apply standard deduplication.

    The data is validated and normalised to the canonical comment schema
    (subreddit_lens.io.schema); non-canonical columns are kept unchanged.
    Deduplication is performed on (author, body, id, created_utc) to remove
    duplicate rows that can appear when scraping sessions overlap. A
    'created_dt' datetime column (UTC, timezone-naive) is added from the Unix
    timestamp.

    Args:
        parquet_path: Path to a Parquet file containing Reddit comment data,
            e.g. produced by subreddit_lens.io.ingest_archive().

    Returns:
        DataFrame with duplicates removed and a 'created_dt' column added.

    Raises:
        FileNotFoundError: If parquet_path does not exist.
        subreddit_lens.io.schema.SchemaError: If a required column is missing.
    """
    df = normalize(_read(parquet_path), "comments", extra_columns="all")
    df = df.drop_duplicates(subset=["author", "body", "id", "created_utc"])
    df["created_dt"] = pd.to_datetime(df["created_utc"], unit="s")
    return df.reset_index(drop=True)


def load_submissions(parquet_path: str | Path) -> pd.DataFrame:
    """Load a Reddit submissions Parquet file.

    The data is validated and normalised to the canonical submission schema;
    non-canonical columns are kept unchanged. If a submission ID appears more
    than once, the last row is kept. A 'created_dt' column is added as in
    load_comments().

    Args:
        parquet_path: Path to a Parquet file containing Reddit submission
            data, e.g. produced by subreddit_lens.io.ingest_archive().

    Returns:
        DataFrame with one row per submission.

    Raises:
        FileNotFoundError: If parquet_path does not exist.
        subreddit_lens.io.schema.SchemaError: If a required column is missing.
    """
    df = normalize(_read(parquet_path), "submissions", extra_columns="all")
    df = df.drop_duplicates(subset="id", keep="last")
    df["created_dt"] = pd.to_datetime(df["created_utc"], unit="s")
    return df.reset_index(drop=True)
