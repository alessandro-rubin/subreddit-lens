"""Plotly figure generation for Reddit network graphs.

Provides interactive visualisations of NetworkX graphs using Plotly,
suitable for display inside Jupyter notebooks or export to HTML.
"""

from __future__ import annotations

from collections.abc import Hashable

import networkx as nx
import plotly.graph_objects as go


def generate_graph_figure[N: Hashable](G: nx.Graph[N]) -> go.Figure:
    """Generate an interactive Plotly scatter-plot visualisation of a graph.

    Nodes must have a 'pos' attribute containing (x, y) coordinate tuples,
    set before calling this function via a layout algorithm such as
    nx.spring_layout(). Node colour encodes degree (in + out for directed graphs).

    Args:
        G: NetworkX graph (directed or undirected) with 'pos' node attributes
            containing (x, y) coordinate tuples for every node.

    Returns:
        Plotly Figure with edge line traces and a node scatter trace. Hovering
        over a node shows its ID and the list of its immediate neighbours.

    Raises:
        KeyError: If any node in G is missing a 'pos' attribute.

    Example:
        >>> import networkx as nx
        >>> G = nx.karate_club_graph()
        >>> pos = nx.spring_layout(G, seed=42)
        >>> nx.set_node_attributes(G, pos, "pos")
        >>> fig = generate_graph_figure(G)
        >>> fig.show()
    """
    pos = nx.get_node_attributes(G, "pos")
    missing = set(G.nodes()) - set(pos.keys())
    if missing:
        raise KeyError(
            f"{len(missing)} node(s) are missing a 'pos' attribute. "
            "Run a layout algorithm first, e.g.:\n"
            "    nx.set_node_attributes(G, nx.spring_layout(G), 'pos')"
        )

    # All edges in one trace, separated by None: one trace per edge makes
    # Plotly unusably slow beyond a few thousand edges.
    edge_x: list[float | None] = []
    edge_y: list[float | None] = []
    for u, v in G.edges():
        edge_x.extend([pos[u][0], pos[v][0], None])
        edge_y.extend([pos[u][1], pos[v][1], None])
    edge_trace = go.Scatter(
        x=edge_x,
        y=edge_y,
        mode="lines",
        line=dict(width=1, color="black"),
        hoverinfo="none",
    )

    connectivity = [G.degree(n) for n in G.nodes()]
    hovertext = [f"Node {n}<br>Neighbors: {list(G.neighbors(n))}" for n in G.nodes()]
    node_trace = go.Scatter(
        x=[pos[n][0] for n in G.nodes()],
        y=[pos[n][1] for n in G.nodes()],
        mode="markers",
        hovertext=hovertext,
        hoverinfo="text",
        marker=dict(size=10, color=connectivity, colorscale="Viridis", showscale=True),
    )

    return go.Figure(
        data=[edge_trace, node_trace],
        layout=go.Layout(
            showlegend=False,
            hovermode="closest",
            margin=dict(b=0, l=0, r=0, t=0),
            xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        ),
    )
