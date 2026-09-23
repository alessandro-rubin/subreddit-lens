"""Posting habit analysis for Reddit users.

Computes probability density functions of hourly posting activity using
kernel density estimation (KDE) with periodic boundary conditions (since
hours 0 and 23 are adjacent on the clock). Also provides Jensen-Shannon
similarity between user activity distributions for downstream clustering.
"""

import numpy as np
import pandas as pd
from scipy.spatial.distance import jensenshannon
from scipy.stats import gaussian_kde


def compute_posting_habits_pdf(
    df: pd.DataFrame,
    author_list: list[str],
    x_grid: np.ndarray,
) -> dict[str, np.ndarray]:
    """Estimate the hourly posting activity distribution for each author.

    Uses kernel density estimation (KDE) with periodic (circular) boundary
    conditions. Posting hours are mirrored at h-24 and h+24 before fitting
    the KDE, and the resulting density is multiplied by 3 to compensate for
    the tripling of data points introduced by the mirroring.

    Args:
        df: DataFrame with 'author' and 'created_utc' columns. The
            'created_utc' column should contain Unix timestamps (int or float).
        author_list: Usernames for which to compute densities. Authors not
            present in df are silently skipped.
        x_grid: 1-D array of hour values at which to evaluate the KDE,
            typically np.linspace(0, 24, 1000).

    Returns:
        Dict mapping each author string to a 1-D numpy array of density
        values evaluated at x_grid. Authors with fewer than 2 posts are
        excluded (KDE requires at least 2 data points).
    """
    author_densities: dict[str, np.ndarray] = {}

    for author in author_list:
        author_hours = pd.to_datetime(
            df[df["author"] == author]["created_utc"], unit="s"
        ).dt.hour

        if len(author_hours) < 2:
            # KDE requires at least 2 data points
            continue

        # Mirror data at the 0/24 boundary for periodic (circular) boundary
        # conditions so the KDE wraps correctly around midnight.
        mirrored_hours = np.concatenate(
            [author_hours - 24, author_hours, author_hours + 24]
        )
        kde = gaussian_kde(mirrored_hours, bw_method=0.05)
        # Multiply by 3 to undo the density dilution from tripling data points.
        density = kde.evaluate(x_grid) * 3
        author_densities[author] = density

    return author_densities


def js_similarity(densities: dict[str, np.ndarray]) -> np.ndarray:
    """Compute a pairwise Jensen-Shannon similarity matrix from density arrays.

    Jensen-Shannon divergence is symmetric and bounded in [0, 1]. Similarity
    is defined as 1 - JS_divergence, so identical distributions score 1.0
    and maximally different distributions score 0.0.

    Args:
        densities: Dict mapping author names to 1-D probability density
            arrays. All arrays must have the same length.

    Returns:
        Square numpy array of shape (n_authors, n_authors) containing
        pairwise similarity scores. Row and column order matches the
        insertion order of densities.keys().
    """
    item_list = list(densities.keys())
    dim = len(item_list)
    similarity_matrix = np.zeros((dim, dim))

    for i, key_i in enumerate(item_list):
        for j, key_j in enumerate(item_list):
            js_div = jensenshannon(densities[key_i], densities[key_j])
            similarity_matrix[i, j] = 1.0 - js_div

    return similarity_matrix
