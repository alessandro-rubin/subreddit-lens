"""Tests for subreddit_lens.text."""

import pytest

from subreddit_lens.text import preprocess


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("[link text](https://example.com)", "link text"),
        ("Tom &amp; Jerry", "Tom & Jerry"),
        ("a &lt; b", "a < b"),
        # Quote blocks with real newlines (regression: the old pattern only
        # matched the literal characters backslash-n).
        ("&gt; quoted line\n\nactual reply", "actual reply"),
        ("> quoted line\n\nactual reply", "actual reply"),
        # A quote continues until the next blank line.
        ("> first\nsecond\n\nreply", "reply"),
        # Several quotes and replies interleaved.
        ("> q1\n\nr1\n\n> q2\n\nr2", "r1 r2"),
        # A quote at the end of the text.
        ("reply\n\n> trailing quote", "reply"),
        # Escaped newlines from older scrapes.
        ("&gt; quoted\\n\\nreply", "reply"),
        # '>' in the middle of a line is not a quote.
        ("a > b is true", "a > b is true"),
        # Markdown escapes.
        ("l'ho detto \\_ciao\\_ e \\*bene\\*", "l'ho detto _ciao_ e *bene*"),
        # Whitespace is collapsed and non-ASCII characters are kept.
        ("  perché\t\nnon   così  ", "perché non così"),
        ("", ""),
    ],
)
def test_preprocess(raw: str, expected: str) -> None:
    assert preprocess(raw) == expected


@pytest.mark.parametrize("value", [None, 3.0, float("nan")])
def test_non_string_input_returns_empty_string(value: object) -> None:
    assert preprocess(value) == ""  # type: ignore[arg-type]
