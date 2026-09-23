"""Text preprocessing utilities for Reddit comments.

These functions clean raw Reddit comment bodies for downstream NLP tasks.
They preserve non-ASCII characters (e.g. Italian accented letters) and do
not perform language-specific stemming or stopword removal, which belongs
in the NLP pipeline chosen for the analysis.
"""

import html
import re

# Markdown link: [display text](url)
_LINK_PATTERN = re.compile(r"\[(.+?)\]\(.*?\S.*?\)")

# Markdown quote block: a line starting with '>' and everything up to the next
# blank line (Markdown lazy continuation) or the end of the text.
_QUOTE_PATTERN = re.compile(r"^[ \t]*>.*?(?:\n[ \t]*\n|\Z)", re.MULTILINE | re.DOTALL)

# Backslash escapes of Markdown punctuation, e.g. '\*' or '\_'.
_MARKDOWN_ESCAPE_PATTERN = re.compile(r"\\([\\`*_{}\[\]()#+\-.!>~|^])")

_WHITESPACE_PATTERN = re.compile(r"\s+")


def preprocess(text: str | None) -> str:
    """Clean a raw Reddit comment body for NLP processing.

    Steps, in order:

    1. Literal two-character '\\n' sequences, found in some older scrapes
       where newlines were escaped, are turned into real newlines.
    2. HTML entities are decoded ('&gt;' becomes '>', '&amp;' becomes '&').
       Reddit bodies encode quote markers as '&gt;', so this must happen
       before quote removal.
    3. Markdown quote blocks (a line starting with '>' up to the next blank
       line) are removed, since they repeat another user's text.
    4. Markdown links are replaced by their display text.
    5. Markdown backslash escapes are removed ('\\*' becomes '*').
    6. Whitespace is collapsed to single spaces.

    This function does not perform stemming, stopword removal, or
    language-specific tokenisation. Use it as a first-pass cleaner before
    passing text to an NLP pipeline.

    Args:
        text: Raw comment body as returned by the Reddit/Pushshift API.
            Non-string inputs (e.g. None for missing bodies) return an
            empty string rather than raising an error.

    Returns:
        Cleaned text on a single line.

    Examples:
        >>> preprocess("[link text](https://example.com)")
        'link text'
        >>> preprocess("&gt; quoted line\\n\\nactual reply")
        'actual reply'
        >>> preprocess("Tom &amp; Jerry")
        'Tom & Jerry'
        >>> preprocess(None)
        ''
    """
    if not isinstance(text, str):
        return ""

    text = text.replace("\\n", "\n")
    text = html.unescape(text)
    text = _QUOTE_PATTERN.sub("\n", text)
    text = _LINK_PATTERN.sub(r"\1", text)
    text = _MARKDOWN_ESCAPE_PATTERN.sub(r"\1", text)
    return _WHITESPACE_PATTERN.sub(" ", text).strip()
