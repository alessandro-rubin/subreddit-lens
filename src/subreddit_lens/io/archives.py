"""Readers for zstd-compressed Reddit archives.

Supports streaming zstd-compressed JSON-lines files (Pushshift/Arctic
Shift archives). All file paths accept both strings and pathlib.Path objects.
"""

import io
import json
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import zstandard as zstd


def extract_zstd(
    filepath: str | Path,
    condition: Callable[[dict[str, Any]], bool] | None = None,
) -> Iterator[dict[str, Any]]:
    """Stream-process a zstd-compressed JSON-lines file, yielding matching objects.

    Decompresses the file on-the-fly without loading it entirely into
    memory. Each line is expected to be a valid JSON object (newline-
    delimited JSON / NDJSON format, as used by Pushshift archives).

    Args:
        filepath: Path to the .zst compressed file.
        condition: Optional callable that takes a dict and returns bool.
            Only objects for which condition returns True are yielded.
            If None, all objects are yielded.

    Yields:
        dict: Parsed JSON objects satisfying the condition.

    Raises:
        FileNotFoundError: If filepath does not exist.
        zstandard.ZstdError: If the file is not valid zstd-compressed data.
        json.JSONDecodeError: If a line cannot be parsed as JSON.
    """
    filepath = Path(filepath)
    if not filepath.exists():
        raise FileNotFoundError(f"Archive not found: {filepath}")

    with open(filepath, "rb") as compressed_file:
        dctx = zstd.ZstdDecompressor(max_window_size=2_147_483_648)
        with dctx.stream_reader(compressed_file) as stream_reader:
            text_content = io.TextIOWrapper(stream_reader, encoding="utf-8")
            for line in text_content:
                if not line.strip():
                    continue
                obj = json.loads(line)
                if condition is None or condition(obj):
                    yield obj
