"""Smoke tests for the package layout, public API and CLI entry point."""

import importlib

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
