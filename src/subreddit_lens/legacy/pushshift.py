"""Legacy Pushshift scraper for Reddit comment data.

The Pushshift API was significantly restricted in mid-2023. This module is
retained for historical reference. For current data collection workflows,
prefer downloading pre-archived .zst files from the Arctic Shift project
(https://arctic-shift.photon-reddit.com) and loading them with
subreddit_lens.io.extract_zstd().
"""

import logging
from datetime import datetime
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)


def scrape_subreddit_comments(
    subreddit: str,
    after: datetime,
    before: datetime,
    output_path: str | Path,
    limit: int = 1_000_000,
) -> pd.DataFrame:
    """Scrape comments from a subreddit using the Pushshift API via pmaw.

    Retrieves comments posted between 'after' and 'before', saves the
    result to a Parquet file, and returns it as a DataFrame.

    Warning:
        The Pushshift API has been heavily restricted since 2023. This
        function may raise connection errors or return empty results
        depending on current API availability. Consider using pre-downloaded
        .zst archives instead.

    Args:
        subreddit: Subreddit name without the 'r/' prefix (e.g. 'litigi').
        after: Start of the time range (inclusive).
        before: End of the time range (inclusive).
        output_path: File path (without extension) where the resulting
            Parquet file will be written. The parent directory must exist.
        limit: Maximum number of comments to retrieve. Default is 1,000,000.

    Returns:
        DataFrame of scraped comments written to output_path + '.parquet'.

    Raises:
        ImportError: If the 'pmaw' package is not installed.
        RuntimeError: If the Pushshift API returns no data.
    """
    try:
        from pmaw import PushshiftAPI  # type: ignore[import]
    except ImportError as exc:
        raise ImportError(
            "pmaw is not installed. Install it with: "
            "uv add 'subreddit-lens[legacy]'\n"
            "Note: pmaw/Pushshift may be non-functional as of 2023."
        ) from exc

    after_ts = int(after.timestamp())
    before_ts = int(before.timestamp())

    api = PushshiftAPI()
    parameters = {
        "subreddit": subreddit,
        "size": limit,
        "until": before_ts,
        "since": after_ts,
    }
    gen = api.search_comments(**parameters)

    comments = pd.DataFrame([comment for comment in gen])
    if comments.empty:
        raise RuntimeError(
            f"No comments retrieved for r/{subreddit} between {after} and {before}. "
            "The Pushshift API may be unavailable."
        )

    output_path = Path(output_path).with_suffix(".parquet")
    comments.to_parquet(output_path)
    logger.info("Saved %d comments to %s", len(comments), output_path)
    return comments
