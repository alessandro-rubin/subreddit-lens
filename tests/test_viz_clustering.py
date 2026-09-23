"""Tests for subreddit_lens.viz and subreddit_lens.clustering."""

import networkx as nx
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import pytest

from subreddit_lens.clustering import (
    compute_laplacian,
    order_by_similarity,
    spectral_embedding,
)
from subreddit_lens.viz import generate_graph_figure, plot_similarity_matrix

BLOCKS = np.array(
    [
        [1.0, 0.9, 0.1, 0.1],
        [0.9, 1.0, 0.1, 0.1],
        [0.1, 0.1, 1.0, 0.8],
        [0.1, 0.1, 0.8, 1.0],
    ]
)


class TestGraphFigure:
    def test_returns_figure(self) -> None:
        G = nx.karate_club_graph()
        nx.set_node_attributes(G, nx.spring_layout(G, seed=0), "pos")
        fig = generate_graph_figure(G)
        assert isinstance(fig, go.Figure)

    def test_missing_positions_raise(self) -> None:
        with pytest.raises(KeyError):
            generate_graph_figure(nx.path_graph(3))


def test_plot_similarity_matrix_reorders() -> None:
    labels = ["a", "c", "b", "d"]
    shuffled = BLOCKS[[0, 2, 1, 3]][:, [0, 2, 1, 3]]
    fig = plot_similarity_matrix(
        pd.DataFrame(shuffled, index=labels, columns=labels), order=True
    )
    order = list(fig.data[0].x)
    assert abs(order.index("a") - order.index("b")) == 1
    assert abs(order.index("c") - order.index("d")) == 1


def test_order_by_similarity_keeps_blocks_together() -> None:
    order = order_by_similarity(BLOCKS)
    assert sorted(order.tolist()) == [0, 1, 2, 3]
    position = {int(item): i for i, item in enumerate(order)}
    assert abs(position[0] - position[1]) == 1
    assert abs(position[2] - position[3]) == 1


class TestSpectral:
    def test_laplacian_properties(self) -> None:
        M, S, D = compute_laplacian(S_m=BLOCKS)
        np.testing.assert_allclose(S, BLOCKS)
        np.testing.assert_allclose(D, BLOCKS.sum(axis=1))
        # The normalised similarity has largest eigenvalue 1.
        assert np.linalg.eigvalsh(M).max() == pytest.approx(1.0)
        L, _, _ = compute_laplacian(S_m=BLOCKS, pseudo=False)
        np.testing.assert_allclose(L, np.identity(4) - M)

    def test_laplacian_from_data(self) -> None:
        X = np.array([[0.0, 0.0], [0.0, 1.0]])
        _, S, _ = compute_laplacian(X, rbf_p=1.0)
        np.testing.assert_allclose(S, [[1.0, np.exp(-1.0)], [np.exp(-1.0), 1.0]])

    def test_requires_input(self) -> None:
        with pytest.raises(ValueError):
            compute_laplacian()

    def test_embedding_shape(self) -> None:
        eivals, eivecs = spectral_embedding(None, S_m=BLOCKS, pseudo=True, k=2)
        assert eivals.shape == (2,)
        assert eivecs.shape == (4, 2)
