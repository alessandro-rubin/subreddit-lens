"""Tests for subreddit_lens.io, including an end-to-end round trip."""

import json
from pathlib import Path

import pandas as pd
import pytest
import zstandard as zstd

from subreddit_lens.export import (
    chains_to_prompt_pairs,
    export_prompt_pairs_to_jsonl,
    extract_thread_chains,
)
from subreddit_lens.io import extract_zstd, load_comments, unpack_zst
from subreddit_lens.network import create_nx_graph


@pytest.fixture
def archive(comments_df: pd.DataFrame, tmp_path: Path) -> Path:
    """Write the fixture comments as a zstd-compressed NDJSON archive."""
    lines = [json.dumps(r, ensure_ascii=False) for r in comments_df.to_dict("records")]
    # A trailing blank line, as some dumps have.
    payload = ("\n".join(lines) + "\n\n").encode("utf-8")
    path = tmp_path / "comments.zst"
    path.write_bytes(zstd.ZstdCompressor().compress(payload))
    return path


class TestExtractZstd:
    def test_reads_all_objects(self, archive: Path, comments_df: pd.DataFrame) -> None:
        records = list(extract_zstd(archive))
        assert len(records) == len(comments_df)
        assert records[3]["body"] == "Perché?"

    def test_condition_filters(self, archive: Path) -> None:
        records = list(extract_zstd(archive, condition=lambda r: r["author"] == "bob"))
        assert {r["id"] for r in records} == {"c2", "c8"}

    def test_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            list(extract_zstd(tmp_path / "missing.zst"))


def test_unpack_zst(archive: Path, tmp_path: Path) -> None:
    out = tmp_path / "comments.ndjson"
    unpack_zst(archive, out)
    assert out.read_text(encoding="utf-8").count("\n") == 12


class TestLoadComments:
    def test_deduplicates_and_adds_datetime(
        self, comments_df: pd.DataFrame, tmp_path: Path
    ) -> None:
        path = tmp_path / "comments.parquet"
        pd.concat([comments_df, comments_df.iloc[:2]]).to_parquet(path)
        df = load_comments(path)
        assert len(df) == len(comments_df)
        assert df["created_dt"].iloc[0] == pd.Timestamp("2024-07-01 22:30")

    def test_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_comments(tmp_path / "missing.parquet")


def test_round_trip(archive: Path, tmp_path: Path) -> None:
    """Round trip: zstd archive -> Parquet -> thread graph -> prompt pairs JSONL."""
    parquet = tmp_path / "comments.parquet"
    pd.DataFrame(list(extract_zstd(archive))).to_parquet(parquet)

    df = load_comments(parquet)
    chains = extract_thread_chains(create_nx_graph(df), df)
    pairs = chains_to_prompt_pairs(chains)
    out = tmp_path / "pairs.jsonl"

    assert export_prompt_pairs_to_jsonl(pairs, out) == 7
    first = json.loads(out.read_text(encoding="utf-8").splitlines()[0])
    assert set(first) == {"system", "user", "assistant"}
