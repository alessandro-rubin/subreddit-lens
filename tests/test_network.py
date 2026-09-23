"""Tests for subreddit_lens.network."""

from __future__ import annotations

import networkx as nx
import pandas as pd
import pytest

from subreddit_lens.network import (
    create_nx_graph,
    extract_interaction_graph,
    get_parent_author,
    hindex,
    symmetrize_graph,
)


class TestCreateNxGraph:
    def test_edges_point_from_parent_to_child(self, comments_df: pd.DataFrame) -> None:
        G = create_nx_graph(comments_df)
        assert set(G.edges()) == {
            ("s1", "c1"),
            ("c1", "c2"),
            ("c1", "c3"),
            ("c1", "c7"),
            ("c2", "c4"),
            ("c2", "c11"),
            ("c4", "c5"),
            ("c3", "c6"),
            ("s2", "c8"),
            ("s2", "cX"),
            ("cX", "c9"),
            ("c9", "c10"),
        }

    def test_node_kinds(self, comments_df: pd.DataFrame) -> None:
        kinds = nx.get_node_attributes(create_nx_graph(comments_df), "kind")
        assert kinds["s1"] == kinds["s2"] == "submission"
        assert kinds["cX"] == "missing"
        assert all(kinds[c] == "comment" for c in comments_df["id"])

    def test_missing_parent_is_not_a_root(self, comments_df: pd.DataFrame) -> None:
        # Regression: a parent absent from the data used to become a fake
        # thread root with its own ID as thread_id.
        G = create_nx_graph(comments_df)
        roots = {n for n in G.nodes() if G.in_degree(n) == 0}
        assert roots == {"s1", "s2"}
        assert nx.is_directed_acyclic_graph(G)


class TestInteractionGraph:
    def test_parent_author(self, comments_df: pd.DataFrame) -> None:
        df = get_parent_author(comments_df).set_index("id")
        assert df.loc["c2", "parent_author"] == "alice"
        assert pd.isna(df.loc["c1", "parent_author"])  # reply to submission
        assert pd.isna(df.loc["c9", "parent_author"])  # parent missing
        assert "parent_author" not in comments_df.columns  # input not modified

    def test_default_excludes_deleted_and_bots(self, comments_df: pd.DataFrame) -> None:
        G = extract_interaction_graph(get_parent_author(comments_df))
        assert "[deleted]" not in G
        assert "AutoModerator" not in G
        assert {(u, v): d["weight"] for u, v, d in G.edges(data=True)} == {
            ("bob", "alice"): 1,
            ("carol", "alice"): 1,
            ("alice", "bob"): 1,
            ("alice", "alice"): 1,
            ("alice", "carol"): 1,
            ("carol", "bob"): 1,
        }

    def test_exclusion_can_be_disabled(self, comments_df: pd.DataFrame) -> None:
        G = extract_interaction_graph(
            get_parent_author(comments_df), exclude_authors=None
        )
        assert G.has_edge("[deleted]", "alice")
        assert G.has_edge("AutoModerator", "carol")

    def test_weights_count_replies(self) -> None:
        df = pd.DataFrame(
            {
                "id": ["a", "b", "c"],
                "author": ["u", "v", "v"],
                "parent_author": [None, "u", "u"],
            }
        )
        G = extract_interaction_graph(df)
        assert G["v"]["u"]["weight"] == 2


def test_symmetrize_graph() -> None:
    G: nx.DiGraph[str] = nx.DiGraph()
    G.add_edge("a", "b", weight=3)
    G.add_edge("b", "a", weight=1)
    G.add_edge("a", "c", weight=2)
    S = symmetrize_graph(G)
    assert S["a"]["b"]["weight"] == 4
    assert abs(S["a"]["b"]["delta"]) == 2
    assert S["a"]["c"]["weight"] == 2
    assert S["a"]["c"]["delta"] == 2


class TestHindex:
    def test_star_graph(self) -> None:
        # The centre's neighbours all have degree 1, so h = 1.
        assert hindex(nx.star_graph(5), 0) == 1

    def test_complete_graph(self) -> None:
        # K5: 4 neighbours, each of degree 4.
        assert hindex(nx.complete_graph(5), 0) == 4

    def test_isolated_node(self) -> None:
        G: nx.Graph[str] = nx.Graph()
        G.add_node("a")
        assert hindex(G, "a") == 0

    def test_directed_graph_uses_both_directions(self) -> None:
        # Regression: on a DiGraph only successors used to count, so a user
        # who only receives replies had h-index 0.
        G = nx.DiGraph([("b", "a"), ("c", "a"), ("b", "c"), ("c", "b")])
        assert hindex(G, "a") == 2
        assert hindex(G, "a") == hindex(G.to_undirected(), "a")

    def test_self_loops_are_ignored(self) -> None:
        G = nx.Graph([("a", "a"), ("a", "b"), ("b", "b")])
        assert hindex(G, "a") == 1

    def test_unknown_node_raises(self) -> None:
        with pytest.raises(nx.NetworkXError):
            hindex(nx.Graph(), "missing")
