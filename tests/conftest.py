"""Shared fixtures: a small synthetic comment dataset with known structure.

Thread s1:

    s1 (submission)
    +-- c1 alice
        +-- c2 bob        quotes c1
        |   +-- c4 alice
        |   |   +-- c5 [deleted]   body '[deleted]'
        |   +-- c11 carol
        +-- c3 carol      contains a Markdown link
        |   +-- c6 AutoModerator
        +-- c7 alice      self-reply

Thread s2:

    s2 (submission)
    +-- c8 bob
    +-- cX (not in the data: a missing parent)
        +-- c9 carol
            +-- c10 alice

Submissions (submissions_df): s1 by dave, who never comments, and s2 by
bob, who writes c8 (so c8 has is_submitter=True in
comments_with_submitter_df).

Timestamps are chosen so that local-time conversion is testable: c1 is
posted at 22:30 UTC on 2024-07-01, which is 00:30 on 2024-07-02 in Rome
(CEST, UTC+2).
"""

import json
from pathlib import Path

import pandas as pd
import pytest
import zstandard as zstd

from subreddit_lens.config import Config, load_config

BASE = int(pd.Timestamp("2024-07-01 22:30", tz="UTC").timestamp())

COMMENTS = [
    # id, parent_id, link_id, author, body, minutes after BASE
    ("c1", "t3_s1", "t3_s1", "alice", "Prima risposta", 0),
    ("c2", "t1_c1", "t3_s1", "bob", "&gt; Prima risposta\n\nNon sono d'accordo", 5),
    ("c3", "t1_c1", "t3_s1", "carol", "Vedi [qui](https://example.com)", 10),
    ("c4", "t1_c2", "t3_s1", "alice", "Perché?", 15),
    ("c5", "t1_c4", "t3_s1", "[deleted]", "[deleted]", 20),
    ("c6", "t1_c3", "t3_s1", "AutoModerator", "Messaggio automatico", 25),
    ("c7", "t1_c1", "t3_s1", "alice", "Aggiungo una cosa", 30),
    ("c8", "t3_s2", "t3_s2", "bob", "Nuovo thread", 60),
    ("c9", "t1_cX", "t3_s2", "carol", "Rispondo a un commento mancante", 65),
    ("c10", "t1_c9", "t3_s2", "alice", "Risposta all'orfano", 70),
    ("c11", "t1_c2", "t3_s1", "carol", "Altra risposta a bob", 75),
]


@pytest.fixture
def comments_df() -> pd.DataFrame:
    """Comments DataFrame in the Arctic Shift / Pushshift column layout."""
    df = pd.DataFrame(
        COMMENTS,
        columns=["id", "parent_id", "link_id", "author", "body", "minutes"],
    )
    df["created_utc"] = BASE + df.pop("minutes") * 60
    return df


SUBMISSIONS = [
    # id, author, title
    ("s1", "dave", "Primo post"),
    ("s2", "bob", "Secondo post"),
]


@pytest.fixture
def submissions_df() -> pd.DataFrame:
    """Submissions DataFrame for the two fixture threads."""
    df = pd.DataFrame(SUBMISSIONS, columns=["id", "author", "title"])
    df["created_utc"] = BASE - 3600
    return df


@pytest.fixture
def comments_with_submitter_df(comments_df: pd.DataFrame) -> pd.DataFrame:
    """Comments with the 'is_submitter' flag set by Reddit for OP comments."""
    return comments_df.assign(is_submitter=comments_df["id"] == "c8")


def write_archive(path: Path, df: pd.DataFrame) -> None:
    """Write a DataFrame as a zstd-compressed NDJSON archive."""
    payload = "\n".join(
        json.dumps(r, ensure_ascii=False) for r in df.to_dict("records")
    )
    path.write_bytes(zstd.ZstdCompressor().compress(payload.encode("utf-8")))


@pytest.fixture
def project(
    tmp_path: Path, comments_df: pd.DataFrame, submissions_df: pd.DataFrame
) -> Path:
    """A project directory with a config file and both archives."""
    (tmp_path / "data").mkdir()
    write_archive(tmp_path / "data" / "demo_comments.zst", comments_df)
    write_archive(tmp_path / "data" / "demo_submissions.zst", submissions_df)
    (tmp_path / "subreddit-lens.toml").write_text(
        'subreddit = "demo"\ntimezone = "Europe/Rome"\n', encoding="utf-8"
    )
    return tmp_path


@pytest.fixture
def config(project: Path) -> Config:
    """Configuration of the fixture project (nothing ingested yet)."""
    return load_config(project / "subreddit-lens.toml")
