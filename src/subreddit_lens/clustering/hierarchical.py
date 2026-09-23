"""Hierarchical clustering utilities.

Adapted from the author's clustering_utils repository
(https://github.com/alessandro-rubin/clustering_utils), previously included
in this project as a git submodule.
"""

import numpy as np
from scipy.cluster import hierarchy
from scipy.spatial.distance import squareform


def order_by_similarity(similarity_matrix: np.ndarray) -> np.ndarray:
    """Return a permutation that places similar items next to each other.

    Converts the similarity matrix to a dissimilarity (1 - S), runs
    average-linkage hierarchical clustering, and applies optimal leaf
    ordering to the resulting dendrogram.

    Args:
        similarity_matrix: Square symmetric similarity matrix with values in
            [0, 1] and ones on the diagonal.

    Returns:
        1-D integer array with the optimal ordering of the rows/columns.
    """
    # squareform converts the square matrix into the condensed form expected
    # by hierarchy.linkage.
    D = squareform(1 - similarity_matrix)
    Z = hierarchy.linkage(D, method="average")
    optimal_Z = hierarchy.optimal_leaf_ordering(Z, D)
    return hierarchy.leaves_list(optimal_Z)
