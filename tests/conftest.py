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

Timestamps are chosen so that local-time conversion is testable: c1 is
posted at 22:30 UTC on 2024-07-01, which is 00:30 on 2024-07-02 in Rome
(CEST, UTC+2).
"""

import pandas as pd
import pytest

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
