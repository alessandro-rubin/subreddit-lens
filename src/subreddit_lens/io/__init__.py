"""Data loading from zstd archives and Parquet files."""

from subreddit_lens.io.archives import extract_zstd, unpack_zst
from subreddit_lens.io.ingest import ingest_archive
from subreddit_lens.io.parquet import load_comments, load_submissions
from subreddit_lens.io.schema import (
    COMMENT_FIELDS,
    SUBMISSION_FIELDS,
    SchemaError,
    normalize,
    strip_type_prefix,
)

__all__ = [
    "COMMENT_FIELDS",
    "SUBMISSION_FIELDS",
    "SchemaError",
    "extract_zstd",
    "ingest_archive",
    "load_comments",
    "load_submissions",
    "normalize",
    "strip_type_prefix",
    "unpack_zst",
]
