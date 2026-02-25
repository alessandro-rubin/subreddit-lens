"""Text preprocessing utilities for Italian Reddit comments.

These functions clean raw Reddit comment bodies for downstream NLP tasks.
They preserve Italian characters and do not perform language-specific
stemming or stopword removal, which belongs in analysis notebooks where
the specific NLP pipeline can be chosen.
"""

import re


def preprocess(text: str) -> str:
    """Clean a raw Reddit comment body for NLP processing.

    Removes Markdown hyperlinks (keeping the display text), Reddit quote
    blocks (lines starting with '>'), and normalises whitespace. HTML
    entities for ampersand and greater-than are also collapsed.

    This function does not perform stemming, stopword removal, or
    language-specific tokenisation. Use it as a first-pass cleaner before
    passing text to an NLP pipeline.

    Args:
        text: Raw comment body as returned by the Reddit/Pushshift API.
            Non-string inputs (e.g. None for deleted comments) return an
            empty string rather than raising an error.

    Returns:
        Cleaned text with Markdown links de-bracketed, quote lines removed,
        and whitespace normalised to single spaces.

    Examples:
        >>> preprocess("[link text](https://example.com)")
        'link text'
        >>> preprocess("> quoted line\\n\\nactual reply")
        'actual reply'
        >>> preprocess(None)
        ''
    """
    if not isinstance(text, str):
        return ""

    # Remove Markdown hyperlinks, keeping only the display text.
    # Pattern: [display text](url)
    url_pattern = r"\[(.+?)\]\(.*?\S.*?\)"
    text = re.sub(url_pattern, r"\1", text)

    # Remove Reddit quote blocks: lines beginning with '>' followed by
    # content up to a blank line separator.
    quote_pattern = r">(.+?)\\n\\n"
    text = re.sub(quote_pattern, "", text)

    # Normalise line breaks, tabs, backslashes, and HTML entities to spaces.
    text = re.sub(r"(\n|\t|\\|&amp;|&gt;)", " ", text).strip()

    return text
