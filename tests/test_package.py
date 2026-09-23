"""Smoke tests for the package layout, public API and CLI entry point."""

import importlib

import numpy as np
import pandas as pd
import pytest
from typer.testing import CliRunner

import subreddit_lens
from subreddit_lens.cli import app

SUBPACKAGES = [
    "io",
    "text",
    "network",
    "temporal",
    "export",
    "clustering",
    "viz",
    "legacy",
]


@pytest.mark.parametrize("name", SUBPACKAGES)
def test_subpackage_imports(name: str) -> None:
    importlib.import_module(f"subreddit_lens.{name}")


def test_public_api_is_exported() -> None:
    for name in subreddit_lens.__all__:
        assert hasattr(subreddit_lens, name), name


def test_version_is_set() -> None:
    assert subreddit_lens.__version__ != "0.0.0"


def test_cli_version() -> None:
    result = CliRunner().invoke(app, ["version"])
    assert result.exit_code == 0
    assert result.output.strip() == subreddit_lens.__version__


def test_thread_pipeline_on_tiny_dataset() -> None:
    df = pd.DataFrame(
        {
            "id": ["c1", "c2", "c3"],
            "parent_id": ["t3_s1", "t1_c1", "t1_c2"],
            "link_id": ["t3_s1", "t3_s1", "t3_s1"],
            "author": ["alice", "bob", "alice"],
            "body": ["first", "reply", "reply to reply"],
        }
    )
    G = subreddit_lens.create_nx_graph(df)
    assert set(G.edges()) == {("s1", "c1"), ("c1", "c2"), ("c2", "c3")}

    chains = subreddit_lens.extract_thread_chains(G, df, min_length=2)
    assert len(chains) == 1
    assert [c["author"] for c in chains[0]["chain"]] == ["alice", "bob", "alice"]

    users = subreddit_lens.extract_interaction_graph(
        subreddit_lens.get_parent_author(df)
    )
    assert users["bob"]["alice"]["weight"] == 1
    assert users["alice"]["bob"]["weight"] == 1


def test_order_by_similarity_returns_permutation() -> None:
    S = np.array(
        [
            [1.0, 0.9, 0.1, 0.1],
            [0.9, 1.0, 0.1, 0.1],
            [0.1, 0.1, 1.0, 0.8],
            [0.1, 0.1, 0.8, 1.0],
        ]
    )
    order = subreddit_lens.order_by_similarity(S)
    assert sorted(order.tolist()) == [0, 1, 2, 3]
    # The two blocks {0, 1} and {2, 3} stay contiguous.
    position = {int(item): i for i, item in enumerate(order)}
    assert abs(position[0] - position[1]) == 1
    assert abs(position[2] - position[3]) == 1


def test_compute_laplacian_requires_input() -> None:
    with pytest.raises(ValueError):
        subreddit_lens.compute_laplacian()
