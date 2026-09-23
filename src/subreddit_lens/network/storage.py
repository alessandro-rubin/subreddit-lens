"""Saving and loading graphs, so they are not rebuilt on every run."""

from __future__ import annotations

from pathlib import Path

import networkx as nx


def save_graph(G: nx.Graph[str], path: str | Path) -> None:
    """Write a graph to a GraphML file.

    GraphML keeps node and edge attributes (e.g. 'weight', 'delta', 'kind')
    and the graph's directedness, and can be opened by Gephi, Cytoscape and
    igraph. Attribute values must be strings, numbers or booleans.

    Args:
        G: Graph with string node IDs.
        path: Destination file, conventionally with a '.graphml' extension.
            The parent directory is created if needed.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    nx.write_graphml(G, path)


def load_graph(path: str | Path) -> nx.Graph[str]:
    """Read a graph written by save_graph().

    Args:
        path: GraphML file.

    Returns:
        A DiGraph if the file stores a directed graph, otherwise a Graph,
        with string node IDs.

    Raises:
        FileNotFoundError: If path does not exist.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Graph file not found: {path}")
    graph: nx.Graph[str] = nx.read_graphml(path, node_type=str)
    # read_graphml adds empty GraphML defaults as graph attributes; drop them
    # so that a save/load round trip returns an equal graph.
    for key in ("node_default", "edge_default"):
        if graph.graph.get(key) == {}:
            del graph.graph[key]
    return graph
