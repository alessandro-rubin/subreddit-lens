"""Readers for zstd-compressed Reddit archives.

Supports streaming zstd-compressed JSON-lines files (Pushshift/Arctic
Shift archives). All file paths accept both strings and pathlib.Path objects.
"""

import io
import json
import logging
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import zstandard as zstd

logger = logging.getLogger(__name__)


def extract_zstd(
    filepath: str | Path,
    condition: Callable[[dict[str, Any]], bool] | None = None,
    verbose: bool = False,
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
        verbose: If True, logs a progress message (level INFO) every 1000
            yielded objects. Default is False.

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

    count = 0
    with open(filepath, "rb") as compressed_file:
        dctx = zstd.ZstdDecompressor(max_window_size=2_147_483_648)
        with dctx.stream_reader(compressed_file) as stream_reader:
            text_content = io.TextIOWrapper(stream_reader, encoding="utf-8")
            for line in text_content:
                if not line.strip():
                    continue
                obj = json.loads(line)
                if condition is None or condition(obj):
                    count += 1
                    if verbose and count % 1000 == 0:
                        logger.info("%d objects collected from %s", count, filepath)
                    yield obj


def unpack_zst(in_filepath: str | Path, out_filepath: str | Path) -> None:
    """Decompress a zstd-compressed file to raw bytes on disk.

    Streams the decompression in 64 KB chunks to keep memory usage low
    regardless of file size.

    Args:
        in_filepath: Path to the .zst input file.
        out_filepath: Path to write the decompressed output. The parent
            directory must already exist.

    Raises:
        FileNotFoundError: If in_filepath does not exist.
        zstandard.ZstdError: If the file is not valid zstd-compressed data.
    """
    in_filepath = Path(in_filepath)
    out_filepath = Path(out_filepath)
    if not in_filepath.exists():
        raise FileNotFoundError(f"Input file not found: {in_filepath}")

    dctx = zstd.ZstdDecompressor(max_window_size=2_147_483_648)
    with open(in_filepath, "rb") as ifh, open(out_filepath, "wb") as ofh:
        dctx.copy_stream(ifh, ofh, write_size=2**16)
