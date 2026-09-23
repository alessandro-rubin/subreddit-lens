"""Tests for subreddit_lens.export."""

import json
from pathlib import Path

import networkx as nx
import pandas as pd
import pytest

from subreddit_lens.export import (
    chains_to_prompt_pairs,
    export_chains_to_jsonl,
    export_prompt_pairs_to_jsonl,
    extract_thread_chains,
)
from subreddit_lens.network import create_nx_graph


def chain_ids(chain: dict) -> list[str]:
    return [c["comment_id"] for c in chain["chain"]]


@pytest.fixture
def chains(comments_df: pd.DataFrame) -> list:
    return extract_thread_chains(create_nx_graph(comments_df), comments_df)


class TestExtractThreadChains:
    def test_root_to_leaf_paths(self, chains: list) -> None:
        assert sorted(chain_ids(c) for c in chains) == sorted(
            [
                ["c1", "c2", "c4", "c5"],
                ["c1", "c2", "c11"],
                ["c1", "c3", "c6"],
                ["c1", "c7"],
                ["c9", "c10"],
            ]
        )

    def test_single_comment_chains_are_dropped(self, chains: list) -> None:
        # c8 has no replies, so its chain has length 1 < min_length.
        assert all("c8" not in chain_ids(c) for c in chains)

    def test_orphan_chain_keeps_submission_as_thread_id(self, chains: list) -> None:
        # Regression: the missing parent 'cX' used to be reported as thread_id.
        orphan = next(c for c in chains if chain_ids(c) == ["c9", "c10"])
        assert orphan["thread_id"] == "s2"

    def test_min_length(self, comments_df: pd.DataFrame) -> None:
        G = create_nx_graph(comments_df)
        chains = extract_thread_chains(G, comments_df, min_length=4)
        assert [chain_ids(c) for c in chains] == [["c1", "c2", "c4", "c5"]]

    def test_duplicated_ids_do_not_crash(self, comments_df: pd.DataFrame) -> None:
        edited = comments_df.iloc[[0]].assign(body="Prima risposta (modificato)")
        df = pd.concat([comments_df, edited], ignore_index=True)
        chains = extract_thread_chains(create_nx_graph(df), df)
        bodies = {c["body"] for ch in chains for c in ch["chain"]}
        assert "Prima risposta (modificato)" in bodies
        assert "Prima risposta" not in bodies

    def test_graph_without_kind_attributes(self, comments_df: pd.DataFrame) -> None:
        G = nx.DiGraph(create_nx_graph(comments_df).edges())
        assert len(extract_thread_chains(G, comments_df)) == 5


class TestPromptPairs:
    def test_each_reply_pair_is_emitted_once(self, chains: list) -> None:
        # Regression: (c1, c2) is shared by two chains and used to be emitted
        # twice.
        pairs = chains_to_prompt_pairs(chains, skip_removed=False)
        keys = [(p["user"], p["assistant"]) for p in pairs]
        assert len(keys) == len(set(keys)) == 8

    def test_removed_bodies_are_skipped(self, chains: list) -> None:
        pairs = chains_to_prompt_pairs(chains)
        assert len(pairs) == 7
        assert all(p["assistant"] != "[deleted]" for p in pairs)

    def test_system_prompt(self, chains: list) -> None:
        pairs = chains_to_prompt_pairs(chains, system_prompt="Sei un utente.")
        assert {p["system"] for p in pairs} == {"Sei un utente."}
        assert set(pairs[0]) == {"system", "user", "assistant"}


def test_jsonl_export(chains: list, tmp_path: Path) -> None:
    chains_path = tmp_path / "chains.jsonl"
    assert export_chains_to_jsonl(chains, chains_path) == len(chains)
    lines = chains_path.read_text(encoding="utf-8").splitlines()
    assert [json.loads(line) for line in lines] == chains
    # Non-ASCII characters are written as-is, not escaped.
    assert "Perché?" in chains_path.read_text(encoding="utf-8")

    pairs = chains_to_prompt_pairs(chains)
    pairs_path = tmp_path / "pairs.jsonl"
    assert export_prompt_pairs_to_jsonl(pairs, pairs_path) == len(pairs)
    assert len(pairs_path.read_text(encoding="utf-8").splitlines()) == len(pairs)
