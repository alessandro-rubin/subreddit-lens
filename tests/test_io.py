"""Tests for subreddit_lens.io, including an end-to-end round trip."""

import json
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq
import pytest
import zstandard as zstd

from subreddit_lens.export import (
    chains_to_prompt_pairs,
    export_prompt_pairs_to_jsonl,
    extract_thread_chains,
)
from subreddit_lens.io import (
    COMMENT_FIELDS,
    SchemaError,
    extract_zstd,
    ingest_archive,
    load_comments,
    load_submissions,
    normalize,
    strip_type_prefix,
    unpack_zst,
)
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


class TestSchema:
    def test_normalize_types_and_prefixes(self) -> None:
        raw = pd.DataFrame(
            {
                "id": ["t1_a", "b"],
                "parent_id": ["t3_s", "t1_a"],
                "link_id": ["s", "t3_s"],
                "author": ["x", None],
                "body": ["hi", "ok"],
                "created_utc": ["1700000000", 1700000001],  # old dumps: strings
                "permalink": ["/r/x/1", "/r/x/2"],
            }
        )
        df = normalize(raw, "comments")
        assert list(df["id"]) == ["a", "b"]
        assert list(df["link_id"]) == ["t3_s", "t3_s"]
        assert list(df["parent_id"]) == ["t3_s", "t1_a"]
        assert df["created_utc"].dtype == "Int64"
        assert df["is_submitter"].isna().all()  # optional column added
        assert "permalink" not in df.columns
        assert "permalink" in normalize(raw, "comments", "all").columns

    def test_missing_required_column(self) -> None:
        with pytest.raises(SchemaError, match="body"):
            normalize(pd.DataFrame({"id": ["a"]}), "comments")

    def test_strip_type_prefix(self) -> None:
        ids = pd.Series(["t1_a", "t3_b", "c", "t1_t1_d"])
        assert list(strip_type_prefix(ids)) == ["a", "b", "c", "t1_d"]


class TestIngestArchive:
    def test_chunked_write(
        self, archive: Path, tmp_path: Path, comments_df: pd.DataFrame
    ) -> None:
        out = tmp_path / "sub" / "comments.parquet"
        assert ingest_archive(archive, out, chunk_size=3) == len(comments_df)
        parquet = pq.ParquetFile(out)
        assert parquet.metadata.num_rows == len(comments_df)
        assert parquet.metadata.num_row_groups == 4  # 11 records, chunks of 3
        assert not out.with_name(out.name + ".tmp").exists()

        df = load_comments(out)
        assert list(df.columns[:9]) == [f.name for f in COMMENT_FIELDS]
        assert df["created_dt"].iloc[0] == pd.Timestamp("2024-07-01 22:30")

    def test_extra_columns_and_condition(self, tmp_path: Path) -> None:
        records = [
            {
                "id": str(i),
                "parent_id": "t3_s",
                "link_id": "t3_s",
                "author": "u",
                "body": "b",
                "created_utc": i,
                "gildings": {"gid_1": i},
            }
            for i in range(5)
        ]
        archive = tmp_path / "c.zst"
        payload = "\n".join(json.dumps(r) for r in records).encode()
        archive.write_bytes(zstd.ZstdCompressor().compress(payload))

        out = tmp_path / "c.parquet"
        written = ingest_archive(
            archive,
            out,
            extra_columns=["gildings", "absent"],
            condition=lambda r: r["created_utc"] >= 3,
        )
        assert written == 2
        df = pd.read_parquet(out)
        assert list(df["gildings"]) == ['{"gid_1": 3}', '{"gid_1": 4}']
        assert df["absent"].isna().all()

    def test_submissions(self, tmp_path: Path, submissions_df: pd.DataFrame) -> None:
        archive = tmp_path / "s.zst"
        payload = "\n".join(
            json.dumps(r) for r in submissions_df.to_dict("records")
        ).encode()
        archive.write_bytes(zstd.ZstdCompressor().compress(payload))
        out = tmp_path / "s.parquet"
        assert ingest_archive(archive, out, kind="submissions") == 2
        df = load_submissions(out)
        assert list(df["author"]) == ["dave", "bob"]
        assert df["selftext"].isna().all()

    def test_invalid_chunk_size(self, archive: Path, tmp_path: Path) -> None:
        with pytest.raises(ValueError):
            ingest_archive(archive, tmp_path / "x.parquet", chunk_size=0)

    def test_failed_ingest_leaves_no_file(self, tmp_path: Path) -> None:
        archive = tmp_path / "bad.zst"
        archive.write_bytes(zstd.ZstdCompressor().compress(b'{"id": "a"}\n'))
        out = tmp_path / "bad.parquet"
        with pytest.raises(SchemaError):
            ingest_archive(archive, out)
        assert list(tmp_path.glob("bad.parquet*")) == []
