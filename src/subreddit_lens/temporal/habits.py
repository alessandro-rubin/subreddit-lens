"""Posting habit analysis for Reddit users.

Computes probability density functions of hourly posting activity using
kernel density estimation (KDE) with periodic boundary conditions (since
hours 0 and 24 are the same point on the clock). Also provides
Jensen-Shannon distances and similarities between user activity
distributions for downstream clustering.
"""

from collections.abc import Iterable

import numpy as np
import pandas as pd
from scipy.special import entr

from subreddit_lens.constants import DEFAULT_EXCLUDED_AUTHORS

HOURS_PER_DAY = 24


def local_hour(created_utc: pd.Series, tz: str = "UTC") -> pd.Series:
    """Convert Unix timestamps to fractional hours of the day in a timezone.

    Args:
        created_utc: Unix timestamps in seconds (int or float).
        tz: IANA timezone name, e.g. "Europe/Rome". Daylight saving time is
            handled by the conversion.

    Returns:
        Float Series with values in [0, 24), e.g. 13.5 for 13:30 local time.
    """
    local = pd.to_datetime(created_utc, unit="s", utc=True).dt.tz_convert(tz)
    return local.dt.hour + local.dt.minute / 60 + local.dt.second / 3600


def compute_posting_habits_pdf(
    df: pd.DataFrame,
    author_list: Iterable[str] | None,
    x_grid: np.ndarray,
    tz: str = "UTC",
    min_posts: int = 2,
    bw_method: float = 0.05,
    exclude_authors: Iterable[str] | None = DEFAULT_EXCLUDED_AUTHORS,
) -> dict[str, np.ndarray]:
    """Estimate the hourly posting activity distribution for each author.

    Uses kernel density estimation (KDE) with periodic (circular) boundary
    conditions: posting hours are mirrored at h-24 and h+24 before fitting
    the KDE, so the density wraps correctly around midnight. The density
    evaluated on x_grid is then normalised to integrate to 1 over the grid.

    Args:
        df: DataFrame with 'author' and 'created_utc' columns. The
            'created_utc' column should contain Unix timestamps (int or float).
        author_list: Usernames for which to compute densities. Authors not
            present in df are silently skipped. If None, every author in df
            with at least min_posts posts is used.
        x_grid: 1-D array of hour values at which to evaluate the KDE,
            typically np.linspace(0, 24, 1000). It should cover [0, 24] for
            the normalisation to be meaningful.
        tz: IANA timezone used to compute the local hour of each post.
            Default is "UTC"; use e.g. "Europe/Rome" for an Italian
            subreddit.
        min_posts: Minimum number of posts an author needs to be included.
            Must be at least 2 (KDE requires two data points).
        bw_method: Bandwidth factor passed to scipy.stats.gaussian_kde.
            It is relative to the standard deviation of the mirrored data.
        exclude_authors: Usernames to skip, such as '[deleted]' and bots.
            Pass None to keep every author.

    Returns:
        Dict mapping each author string to a 1-D numpy array of density
        values evaluated at x_grid. Authors with fewer than min_posts posts
        are excluded.

    Raises:
        ValueError: If min_posts is lower than 2.
    """
    if min_posts < 2:
        raise ValueError("min_posts must be at least 2 (KDE needs two points)")

    excluded = set(exclude_authors) if exclude_authors is not None else set()
    hours = local_hour(df["created_utc"], tz=tz)
    grouped = hours.groupby(df["author"])
    sizes = grouped.size()
    eligible = {str(a) for a in sizes.index[sizes >= min_posts]} - excluded

    if author_list is None:
        candidates = sorted(eligible)
    else:
        candidates = [a for a in author_list if a in eligible]

    # Imported here: scipy.stats takes about 0.7 s to import and is only
    # needed by this function, not by `import subreddit_lens` or the CLI.
    from scipy.stats import gaussian_kde

    author_densities: dict[str, np.ndarray] = {}
    for author in candidates:
        author_hours = grouped.get_group(author).to_numpy(dtype=float)

        mirrored_hours = np.concatenate(
            [
                author_hours - HOURS_PER_DAY,
                author_hours,
                author_hours + HOURS_PER_DAY,
            ]
        )
        density = gaussian_kde(mirrored_hours, bw_method=bw_method).evaluate(x_grid)
        area = np.trapezoid(density, x_grid)
        author_densities[author] = density / area if area > 0 else density

    return author_densities


def js_distance_matrix(densities: dict[str, np.ndarray]) -> np.ndarray:
    """Compute the pairwise Jensen-Shannon distance matrix of density arrays.

    Returns the base-2 Jensen-Shannon *distance* (the square root of the
    divergence), a metric bounded in [0, 1], with the same values as
    scipy.spatial.distance.jensenshannon(p, q, base=2). Each array is
    normalised to sum to 1 first. The computation is vectorised, using
    JSD(p, q) = H((p + q) / 2) - (H(p) + H(q)) / 2 with H the Shannon
    entropy, one row against all later rows at a time, so memory stays
    O(n * len(array)).

    Args:
        densities: Dict mapping names to 1-D density arrays. All arrays must
            have the same length.

    Returns:
        Symmetric numpy array of shape (n, n) with zeros on the diagonal. Row
        and column order matches the insertion order of densities.keys().
    """
    n = len(densities)
    distances = np.zeros((n, n))
    if n == 0:
        return distances
    p = np.asarray(list(densities.values()), dtype=float)
    p = p / p.sum(axis=1, keepdims=True)
    entropy = entr(p).sum(axis=1)
    for i in range(n - 1):
        mid_entropy = entr(0.5 * (p[i] + p[i + 1 :])).sum(axis=1)
        divergence = mid_entropy - 0.5 * (entropy[i] + entropy[i + 1 :])
        # Rounding can make identical rows slightly negative.
        row = np.sqrt(np.maximum(divergence / np.log(2), 0.0))
        distances[i, i + 1 :] = row
        distances[i + 1 :, i] = row
    return distances


def js_similarity(densities: dict[str, np.ndarray]) -> np.ndarray:
    """Compute a pairwise Jensen-Shannon similarity matrix from density arrays.

    Similarity is defined as 1 - JS distance (base 2), so identical
    distributions score 1.0 and distributions with disjoint support score
    0.0.

    Args:
        densities: Dict mapping names to 1-D density arrays. All arrays must
            have the same length.

    Returns:
        Symmetric numpy array of shape (n, n) with ones on the diagonal. Row
        and column order matches the insertion order of densities.keys().
    """
    return 1.0 - js_distance_matrix(densities)
