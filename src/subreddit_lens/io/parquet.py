"""Readers for Parquet files produced by the ingestion pipeline."""

from pathlib import Path

import pandas as pd


def load_comments(parquet_path: str | Path) -> pd.DataFrame:
    """Load a Reddit comments Parquet file and apply standard deduplication.

    Deduplication is performed on (author, body, id, created_utc) to remove
    duplicate rows that can appear when scraping sessions overlap. A
    'created_dt' datetime column is added from the Unix timestamp.

    Args:
        parquet_path: Path to a Parquet file containing Reddit comment data
            with at least 'author', 'body', 'id', and 'created_utc' columns.

    Returns:
        DataFrame with duplicates removed and a 'created_dt' column added.

    Raises:
        FileNotFoundError: If parquet_path does not exist.
    """
    parquet_path = Path(parquet_path)
    if not parquet_path.exists():
        raise FileNotFoundError(f"Parquet file not found: {parquet_path}")

    df = pd.read_parquet(parquet_path).drop_duplicates(
        subset=["author", "body", "id", "created_utc"]
    )
    df["created_dt"] = pd.to_datetime(df["created_utc"], unit="s")
    return df
