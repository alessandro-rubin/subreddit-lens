"""Tests for subreddit_lens.viz."""

import networkx as nx
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import pytest

from subreddit_lens.viz import (
    generate_graph_figure,
    order_by_similarity,
    plot_similarity_matrix,
)

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
