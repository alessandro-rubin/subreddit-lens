"""Canonical column schema for Reddit comments and submissions.

Pushshift and Arctic Shift dumps carry dozens of fields whose presence and
types vary between years (for example 'created_utc' is a string in some old
dumps, and 'is_submitter' is missing before 2016). This module defines the
subset of fields the package relies on, with one type per field, and the
functions that bring a raw DataFrame to that shape.

Conventions after normalisation:

- 'id' has no type prefix ('abc123').
- 'parent_id' and 'link_id' keep Reddit's type prefix ('t1_abc123' for a
  comment, 't3_xyz789' for a submission), because the prefix tells whether
  a comment replies to another comment or to the submission.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

import pandas as pd
import pyarrow as pa

Kind = Literal["comments", "submissions"]

_TYPE_PREFIX = r"^t[1-6]_"


class SchemaError(ValueError):
    """Raised when a DataFrame lacks fields required by the schema."""


@dataclass(frozen=True)
class Field:
    """One canonical column.

    Attributes:
        name: Column name, as in the Reddit API.
        dtype: One of 'string', 'int', 'bool'.
        required: Whether the column must be present in the input.
    """

    name: str
    dtype: Literal["string", "int", "bool"]
    required: bool = True


COMMENT_FIELDS: tuple[Field, ...] = (
    Field("id", "string"),
    Field("parent_id", "string"),
    Field("link_id", "string"),
    Field("author", "string"),
    Field("body", "string"),
    Field("created_utc", "int"),
    Field("score", "int", required=False),
    Field("subreddit", "string", required=False),
    Field("is_submitter", "bool", required=False),
)

SUBMISSION_FIELDS: tuple[Field, ...] = (
    Field("id", "string"),
    Field("author", "string"),
    Field("title", "string"),
    Field("created_utc", "int"),
    Field("selftext", "string", required=False),
    Field("score", "int", required=False),
    Field("num_comments", "int", required=False),
    Field("subreddit", "string", required=False),
)

FIELDS: dict[Kind, tuple[Field, ...]] = {
    "comments": COMMENT_FIELDS,
    "submissions": SUBMISSION_FIELDS,
}

_PANDAS_DTYPES = {"string": "string", "int": "Int64", "bool": "boolean"}
_ARROW_TYPES = {"string": pa.string(), "int": pa.int64(), "bool": pa.bool_()}


def strip_type_prefix(ids: pd.Series) -> pd.Series:
    """Remove Reddit type prefixes such as 't1_' or 't3_' from IDs.

    IDs without a prefix are returned unchanged.

    Args:
        ids: Series of Reddit IDs, with or without prefix.

    Returns:
        Series of IDs without prefix.
    """
    return ids.astype("string").str.replace(_TYPE_PREFIX, "", regex=True)


def _coerce(column: pd.Series, dtype: str) -> pd.Series:
    if dtype == "int":
        return pd.to_numeric(column, errors="coerce").astype("Int64")
    if dtype == "bool":
        return column.astype("boolean")
    return column.astype("string")


def normalize(
    df: pd.DataFrame,
    kind: Kind,
    extra_columns: Sequence[str] | Literal["all"] = (),
) -> pd.DataFrame:
    """Bring a raw DataFrame of comments or submissions to the canonical schema.

    Canonical columns are cast to their declared type; optional canonical
    columns missing from df are added as all-missing columns. ID prefixes are
    normalised as described in the module docstring.

    Args:
        df: Raw DataFrame, e.g. built from the records of a zstd dump.
        kind: 'comments' or 'submissions'.
        extra_columns: Non-canonical columns to keep after the canonical
            ones, unchanged. 'all' keeps every column of df. Names missing
            from df are ignored.

    Returns:
        A new DataFrame with the canonical columns first, then the extra
        columns, and a fresh RangeIndex.

    Raises:
        SchemaError: If a required canonical column is missing.
    """
    fields = FIELDS[kind]
    missing = [f.name for f in fields if f.required and f.name not in df.columns]
    if missing:
        raise SchemaError(f"Missing required {kind} columns: {missing}")

    df = df.reset_index(drop=True)
    out = pd.DataFrame(index=df.index)
    for f in fields:
        if f.name in df.columns:
            out[f.name] = _coerce(df[f.name], f.dtype)
        else:
            out[f.name] = pd.Series(
                pd.NA, index=df.index, dtype=_PANDAS_DTYPES[f.dtype]
            )

    out["id"] = strip_type_prefix(out["id"])
    if kind == "comments":
        link = out["link_id"]
        out["link_id"] = link.where(link.str.startswith("t3_"), "t3_" + link)

    canonical = {f.name for f in fields}
    extras = list(df.columns) if extra_columns == "all" else list(extra_columns)
    for name in extras:
        if name in df.columns and name not in canonical:
            out[name] = df[name]
    return out


def arrow_schema(kind: Kind, extra_columns: Sequence[str] = ()) -> pa.Schema:
    """Return the Arrow schema used when writing normalised data to Parquet.

    Args:
        kind: 'comments' or 'submissions'.
        extra_columns: Non-canonical columns, stored as strings.

    Returns:
        pyarrow schema with the canonical fields followed by the extras.
    """
    canonical = [pa.field(f.name, _ARROW_TYPES[f.dtype]) for f in FIELDS[kind]]
    names = {f.name for f in FIELDS[kind]}
    extras = [pa.field(n, pa.string()) for n in extra_columns if n not in names]
    return pa.schema(canonical + extras)
