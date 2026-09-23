"""Streaming conversion of zstd archives to Parquet.

Archives are read record by record and written in fixed-size chunks, so
peak memory depends on the chunk size, not on the size of the archive.
"""

import json
import logging
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from subreddit_lens.io.archives import extract_zstd
from subreddit_lens.io.schema import Kind, arrow_schema, normalize

logger = logging.getLogger(__name__)

DEFAULT_CHUNK_SIZE = 100_000


def _as_text(value: Any) -> str | None:
    """Store an arbitrary JSON value in a string column."""
    if value is None or isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def _to_table(
    records: list[dict[str, Any]],
    kind: Kind,
    extra_columns: Sequence[str],
    schema: pa.Schema,
) -> pa.Table:
    df = normalize(pd.DataFrame.from_records(records), kind, extra_columns)
    for name in extra_columns:
        if name in df.columns:
            df[name] = df[name].map(_as_text).astype("string")
        else:
            df[name] = pd.Series(pd.NA, index=df.index, dtype="string")
    return pa.Table.from_pandas(df, schema=schema, preserve_index=False)


def ingest_archive(
    archive: str | Path,
    output: str | Path,
    kind: Kind = "comments",
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    extra_columns: Sequence[str] = (),
    condition: Callable[[dict[str, Any]], bool] | None = None,
) -> int:
    """Convert a zstd NDJSON archive to a Parquet file with the canonical schema.

    Records are normalised with subreddit_lens.io.schema.normalize() and
    written in row groups of chunk_size records. The file is first written
    under a temporary name and renamed at the end, so an interrupted run
    never leaves a truncated Parquet file behind.

    Args:
        archive: Path to the .zst archive (comments or submissions).
        output: Destination Parquet path. The parent directory is created
            if needed. An existing file is replaced.
        kind: 'comments' or 'submissions'.
        chunk_size: Number of records held in memory and written per row
            group.
        extra_columns: Non-canonical fields to keep (e.g. 'permalink'). They
            are stored as strings; non-string values are JSON-encoded.
        condition: Optional filter on the raw records, e.g. a date range or
            a subreddit name for multi-subreddit dumps.

    Returns:
        Number of rows written.

    Raises:
        ValueError: If chunk_size is not positive.
        FileNotFoundError: If the archive does not exist.
        subreddit_lens.io.schema.SchemaError: If records lack required
            fields.

    Example:
        >>> ingest_archive(
        ...     "data/litigi_comments.zst", "data/litigi_comments.parquet"
        ... )
        1234567
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")

    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_name(output.name + ".tmp")
    extras = list(extra_columns)
    schema = arrow_schema(kind, extras)

    total = 0
    batch: list[dict[str, Any]] = []
    try:
        with pq.ParquetWriter(tmp, schema) as writer:
            for record in extract_zstd(archive, condition=condition):
                batch.append(record)
                if len(batch) >= chunk_size:
                    writer.write_table(_to_table(batch, kind, extras, schema))
                    total += len(batch)
                    batch = []
                    logger.info("%d %s written to %s", total, kind, output)
            if batch:
                writer.write_table(_to_table(batch, kind, extras, schema))
                total += len(batch)
        tmp.replace(output)
    finally:
        tmp.unlink(missing_ok=True)

    logger.info("Finished: %d %s written to %s", total, kind, output)
    return total
