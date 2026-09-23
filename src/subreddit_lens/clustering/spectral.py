"""Spectral embedding utilities.

Adapted from the author's clustering_utils repository
(https://github.com/alessandro-rubin/clustering_utils), previously included
in this project as a git submodule.
"""

import numpy as np
from scipy.sparse.linalg import eigsh
from scipy.spatial import distance


def compute_laplacian(
    X: np.ndarray | None = None,
    rbf_p: float = 1.0,
    S_m: np.ndarray | None = None,
    pseudo: bool = True,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Compute the symmetric normalised Laplacian of a similarity matrix.

    If no similarity matrix is given, one is built from X with an RBF
    (Gaussian) kernel on squared Euclidean distances.

    Args:
        X: Data matrix of shape (n_samples, n_features). Ignored when S_m
            is provided.
        rbf_p: RBF kernel coefficient (gamma) used when building S_m from X.
        S_m: Precomputed similarity matrix of shape (n_samples, n_samples).
        pseudo: If True, return the normalised similarity D^-1/2 S D^-1/2
            (the "pseudo Laplacian", I - L). If False, return the normalised
            Laplacian L = I - D^-1/2 S D^-1/2.

    Returns:
        Tuple (M, S_m, D) with the (pseudo) Laplacian, the similarity matrix
        and the degree vector.

    Raises:
        ValueError: If neither X nor S_m is provided.
    """
    if S_m is None:
        if X is None:
            raise ValueError(
                "Either the similarity matrix or the data must be provided"
            )
        S_m = np.exp(-rbf_p * distance.cdist(X, X, metric="sqeuclidean"))

    D = S_m.sum(axis=1)
    D_n = np.sqrt(1 / D)
    M = np.multiply(D_n[np.newaxis, :], np.multiply(S_m, D_n[:, np.newaxis]))
    if not pseudo:
        M = np.identity(M.shape[0]) - M

    return M, S_m, D


def spectral_embedding(
    X: np.ndarray | None,
    rbf_p: float = 1.0,
    S_m: np.ndarray | None = None,
    threshold: float | None = None,
    pseudo: bool = False,
    k: int = 10,
) -> tuple[np.ndarray, np.ndarray]:
    """Compute the spectral embedding of a dataset.

    Args:
        X: Data matrix of shape (n_samples, n_features). May be None when
            S_m is provided.
        rbf_p: RBF kernel coefficient used when building the similarity
            matrix from X.
        S_m: Precomputed similarity matrix of shape (n_samples, n_samples).
        threshold: If given, entries of the (pseudo) Laplacian below this
            value are set to zero before the eigendecomposition.
        pseudo: Passed to compute_laplacian().
        k: Number of eigenvalues and eigenvectors to compute.

    Returns:
        Tuple (eigenvalues, eigenvectors) as returned by
        scipy.sparse.linalg.eigsh (largest-magnitude eigenvalues).
    """
    M, _, _ = compute_laplacian(X, rbf_p, S_m, pseudo=pseudo)
    if threshold is not None:
        M = np.where(M < threshold, 0, M)  # noqa: SIM300
    eivals, eivecs = eigsh(M, k=k)
    return eivals, eivecs
