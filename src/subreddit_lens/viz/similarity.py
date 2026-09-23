"""Heatmap visualisation of similarity matrices.

Adapted from the author's clustering_utils repository
(https://github.com/alessandro-rubin/clustering_utils), previously included
in this project as a git submodule.
"""

from typing import Any

import pandas as pd
import plotly.graph_objects as go

from subreddit_lens.clustering.hierarchical import order_by_similarity


def plot_similarity_matrix(
    similarity_df: pd.DataFrame,
    title: str | None = None,
    axis_title: str | None = None,
    colorscale: str = "Viridis",
    size: int = 1200,
    order: bool = False,
    zmin: float | None = None,
    **kwargs: Any,
) -> go.Figure:
    """Plot a square similarity matrix as an interactive heatmap.

    Args:
        similarity_df: Square DataFrame whose index and columns are the item
            labels (e.g. usernames) and whose values are similarities.
        title: Figure title.
        axis_title: Title used for both axes.
        colorscale: Plotly colour scale name.
        size: Width and height of the figure in pixels.
        order: If True, reorder rows and columns with order_by_similarity()
            so that clusters appear as blocks along the diagonal.
        zmin: Lower bound of the colour scale. The upper bound is fixed at 1.
        **kwargs: Extra keyword arguments passed to Figure.update_layout().

    Returns:
        Plotly Figure containing the heatmap.
    """
    if order:
        labels = similarity_df.columns.to_numpy()
        matrix = similarity_df.to_numpy()
        optimal_order = order_by_similarity(matrix)
        reordered_labels = list(labels[optimal_order])
        similarity_df = pd.DataFrame(
            matrix[optimal_order][:, optimal_order],
            index=reordered_labels,
            columns=reordered_labels,
        )

    fig = go.Figure(
        data=go.Heatmap(
            z=similarity_df.to_numpy(),
            x=similarity_df.columns,
            y=similarity_df.index,
            colorscale=colorscale,
            zmax=1,
            zmin=zmin,
            colorbar={"title": "Similarity"},
        )
    )
    fig.update_layout(
        title=title,
        xaxis={"title": axis_title},
        yaxis={"title": axis_title},
        width=size,
        height=size,
        template="plotly_white",
        **kwargs,
    )
    return fig
