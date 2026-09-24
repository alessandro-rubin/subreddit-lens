"""Tests for subreddit_lens.explore, the exploration CLI and the MCP server.

Expected values follow the fixture threads documented in conftest.py.
"""

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import anyio
import pandas as pd
import pytest
from mcp import Client
from typer.testing import CliRunner

from subreddit_lens import pipeline
from subreddit_lens.cli import app
from subreddit_lens.config import Config
from subreddit_lens.explore import Explorer, QueryError, to_json, to_jsonable
from subreddit_lens.guide import GUIDE
from subreddit_lens.mcp_server import build_server


@pytest.fixture
def explorer(config: Config) -> Iterator[Explorer]:
    pipeline.run_ingest(config)
    with Explorer(config) as ex:
        yield ex


@pytest.fixture
def explorer_no_submissions(config: Config) -> Iterator[Explorer]:
    config.submissions_archive.unlink()
    pipeline.run_ingest(config)
    with Explorer(config) as ex:
        yield ex


class TestViews:
    def test_replies_resolve_comment_and_submission_parents(
        self, explorer: Explorer
    ) -> None:
        replies = explorer.sql(
            "SELECT comment_id, parent_author, parent_kind FROM replies"
        ).set_index("comment_id")
        # c5 ([deleted]) and c6 (AutoModerator) are excluded; c9's parent is
        # missing from the data.
        assert set(replies.index) == {"c1", "c2", "c3", "c4", "c7", "c8", "c10", "c11"}
        assert replies.loc["c1", "parent_author"] == "dave"
        assert replies.loc["c1", "parent_kind"] == "submission"
        assert replies.loc["c2", "parent_author"] == "alice"

    def test_users(self, explorer: Explorer) -> None:
        users = explorer.sql("SELECT * FROM users").set_index("author")
        assert set(users.index) == {"alice", "bob", "carol", "dave"}
        assert users.loc["alice", "n_comments"] == 4
        assert users.loc["alice", "replies_sent"] == 3
        assert users.loc["alice", "replies_received"] == 2
        assert users.loc["dave", "n_comments"] == 0
        assert users.loc["dave", "n_submissions"] == 1

    def test_threads(self, explorer: Explorer) -> None:
        threads = explorer.sql("SELECT * FROM threads").set_index("thread_id")
        assert threads.loc["s1", "n_comments"] == 8
        assert threads.loc["s1", "title"] == "Primo post"
        assert threads.loc["s2", "submitter"] == "bob"

    def test_created_at_is_local_time(self, explorer: Explorer) -> None:
        first = explorer.sql("SELECT created_at FROM comments WHERE id = 'c1'")
        # 22:30 UTC on 1 July is 00:30 in Rome (CEST).
        assert pd.Timestamp(first["created_at"].iloc[0]) == pd.Timestamp(
            "2024-07-02 00:30"
        )

    def test_without_submissions_replies_to_posts_are_unknown(
        self, explorer_no_submissions: Explorer
    ) -> None:
        ex = explorer_no_submissions
        assert not ex.has_submissions
        kinds = ex.sql("SELECT DISTINCT parent_kind FROM replies")["parent_kind"]
        assert list(kinds) == ["comment"]
        assert ex.summary()["n_submissions"] is None


class TestAnalyses:
    def test_summary(self, explorer: Explorer) -> None:
        summary = explorer.summary()
        assert summary["n_comments"] == 11
        assert summary["n_submissions"] == 2
        assert summary["n_threads"] == 2
        assert summary["busiest_hour"] == 0
        assert summary["has_network_metrics"] is False
        json.loads(to_json(summary))  # serialisable

    def test_top_users(self, explorer: Explorer) -> None:
        assert explorer.top_users("replies_sent", n=1)["author"].iloc[0] == "alice"
        assert len(explorer.top_users("comments", n=2)) == 2
        with pytest.raises(QueryError, match="metrics"):
            explorer.top_users("pagerank")
        with pytest.raises(QueryError, match="Unknown ranking"):
            explorer.top_users("karma")  # type: ignore[arg-type]

    def test_pagerank_after_metrics_step(self, config: Config) -> None:
        pipeline.run_ingest(config)
        pipeline.run_network(config)
        pipeline.run_metrics(config)
        with Explorer(config) as ex:
            top = ex.top_users("pagerank", n=4)
        assert {"pagerank", "hindex", "community"} <= set(top.columns)
        assert top["pagerank"].is_monotonic_decreasing

    def test_activity(self, explorer: Explorer) -> None:
        hours = explorer.activity("hour")
        assert len(hours) == 24
        assert hours.set_index("hour").loc[[0, 1], "comments"].tolist() == [6, 5]
        weekdays = explorer.activity("weekday")
        assert weekdays["comments"].sum() == 11
        assert explorer.activity("month")["comments"].sum() == 11
        assert explorer.activity("hour", author="bob")["comments"].sum() == 2

    def test_user_profile(self, explorer: Explorer) -> None:
        profile = explorer.user("alice")
        assert profile["n_comments"] == 4
        assert set(profile["replies_to"]["author"]) == {"bob", "carol", "dave"}
        assert set(profile["replied_by"]["author"]) == {"bob", "carol"}
        assert len(profile["recent_comments"]) == 4
        json.loads(to_json(profile))

    def test_unknown_user_suggests_names(self, explorer: Explorer) -> None:
        with pytest.raises(QueryError, match="alice"):
            explorer.user("alcie")

    def test_thread_reading_order(self, explorer: Explorer) -> None:
        s1 = explorer.thread("t3_s1")
        assert s1["id"].tolist() == ["c1", "c2", "c4", "c5", "c11", "c3", "c6", "c7"]
        assert s1["depth"].tolist() == [1, 2, 3, 4, 3, 2, 3, 2]
        # c9's parent is missing: shown as top-level with its reply below it.
        s2 = explorer.thread("s2")
        assert s2["id"].tolist() == ["c8", "c9", "c10"]
        assert s2["depth"].tolist() == [1, 1, 2]
        with pytest.raises(QueryError):
            explorer.thread("nope")

    def test_search_decodes_html(self, explorer: Explorer) -> None:
        found = explorer.search("RISPOSTA")
        assert set(found["id"]) == {"c1", "c2", "c10", "c11"}
        c2 = str(found.set_index("id").loc["c2", "body"])
        assert c2.startswith("> Prima risposta")  # '&gt;' decoded
        assert len(explorer.search("risposta", author="carol")) == 1
        assert explorer.search("risposta", max_chars=5)["body"].str.len().max() <= 5

    def test_interactions(self, explorer: Explorer) -> None:
        pairs = explorer.interactions()
        assert len(pairs) == 6  # self-replies and excluded authors removed
        assert (pairs["author"] != pairs["parent_author"]).all()
        with_bob = explorer.interactions(author="bob")
        assert (
            (with_bob["author"] == "bob") | (with_bob["parent_author"] == "bob")
        ).all()


class TestSql:
    def test_select(self, explorer: Explorer) -> None:
        result = explorer.sql("SELECT count(*) AS n FROM comments")
        assert result["n"].iloc[0] == 11
        assert len(explorer.sql("SELECT * FROM comments", limit=3)) == 3

    @pytest.mark.parametrize(
        ("query", "message"),
        [
            ("DELETE FROM comments", "Only SELECT"),
            ("CREATE TABLE x AS SELECT 1", "Only SELECT"),
            ("SELECT 1; SELECT 2", "exactly one"),
            ("SELEC 1", "Invalid SQL"),
            ("SELECT * FROM read_csv('/etc/passwd')", "Permission"),
            ("SELECT * FROM no_such_view", "no_such_view"),
        ],
    )
    def test_rejected(self, explorer: Explorer, query: str, message: str) -> None:
        with pytest.raises(QueryError, match=message):
            explorer.sql(query)

    def test_settings_are_locked(self, explorer: Explorer) -> None:
        with pytest.raises(QueryError):
            explorer.sql("SELECT set_config('enable_external_access', 'true')")

    def test_schema(self, explorer: Explorer) -> None:
        schema = explorer.schema()
        assert {"comments", "submissions", "replies", "users", "threads"} <= set(schema)
        columns = {c["column"] for c in schema["comments"]}
        assert {"thread_id", "created_at", "body"} <= columns


def test_to_jsonable_handles_missing_values() -> None:
    df = pd.DataFrame(
        {
            "t": [pd.Timestamp("2024-01-01"), pd.NaT],
            "x": [1.5, float("nan")],
            "s": pd.array(["a", pd.NA], dtype="string"),
        }
    )
    assert to_jsonable(df) == [
        {"t": "2024-01-01T00:00:00", "x": 1.5, "s": "a"},
        {"t": None, "x": None, "s": None},
    ]


def test_explorer_requires_ingested_data(config: Config) -> None:
    with pytest.raises(FileNotFoundError, match="ingest"):
        Explorer(config)


class TestCli:
    runner = CliRunner()

    def invoke(self, project: Path, *args: str) -> tuple[int, str]:
        config = str(project / "subreddit-lens.toml")
        result = self.runner.invoke(app, [args[0], "--config", config, *args[1:]])
        return result.exit_code, result.output

    def test_commands(self, project: Path) -> None:
        assert self.invoke(project, "ingest")[0] == 0
        code, output = self.invoke(project, "summary")
        assert code == 0, output
        assert json.loads(output)["n_comments"] == 11

        code, output = self.invoke(project, "users", "--by", "replies_sent", "-n", "1")
        assert code == 0, output
        assert "alice" in output

        code, output = self.invoke(project, "sql", "SELECT id FROM comments", "--json")
        assert code == 0, output
        assert len(json.loads(output)) == 11

        for command in (
            ["user", "alice"],
            ["activity", "--by", "weekday"],
            ["threads"],
            ["thread", "s1"],
            ["search", "risposta"],
            ["interactions", "--author", "bob"],
            ["schema"],
        ):
            code, output = self.invoke(project, *command)
            assert code == 0, (command, output)

    def test_errors_are_one_line(self, project: Path) -> None:
        self.invoke(project, "ingest")
        code, output = self.invoke(project, "sql", "DROP VIEW comments")
        assert code == 1
        assert "Only SELECT" in output
        code, output = self.invoke(project, "user", "alcie")
        assert code == 1
        assert "alice" in output

    def test_before_ingest(self, project: Path) -> None:
        code, output = self.invoke(project, "summary")
        assert code == 1
        assert "ingest" in output

    def test_guide(self) -> None:
        result = self.runner.invoke(app, ["guide"])
        assert result.exit_code == 0
        assert result.output.strip() == GUIDE.strip()


class TestMcpServer:
    def call(self, explorer: Explorer, name: str, args: dict[str, Any]) -> Any:
        async def run() -> Any:
            async with Client(build_server(explorer)) as client:
                return await client.call_tool(name, args)

        return anyio.run(run)

    def test_tools_are_read_only(self, explorer: Explorer) -> None:
        async def run() -> Any:
            async with Client(build_server(explorer)) as client:
                return await client.list_tools()

        tools = anyio.run(run).tools
        assert {t.name for t in tools} == {
            "summary",
            "schema",
            "top_users",
            "user_profile",
            "activity",
            "top_threads",
            "thread",
            "search",
            "interactions",
            "run_sql",
        }
        assert all(t.annotations and t.annotations.read_only_hint for t in tools)

    def test_structured_results(self, explorer: Explorer) -> None:
        result = self.call(explorer, "summary", {})
        assert not result.is_error
        assert result.structured_content["n_comments"] == 11
        result = self.call(explorer, "run_sql", {"query": "SELECT 1 AS one"})
        assert result.structured_content == {"result": [{"one": 1}]}

    @pytest.mark.parametrize(
        ("name", "args"),
        [
            ("schema", {}),
            ("top_users", {"by": "replies_sent", "n": 2}),
            ("user_profile", {"author": "alice", "max_chars": 20}),
            ("activity", {"by": "weekday", "author": "bob"}),
            ("top_threads", {"by": "authors"}),
            ("thread", {"thread_id": "s1", "max_comments": 3}),
            ("search", {"text": "risposta", "n": 2}),
            ("interactions", {"author": "alice"}),
        ],
    )
    def test_every_tool_answers(
        self, explorer: Explorer, name: str, args: dict[str, Any]
    ) -> None:
        result = self.call(explorer, name, args)
        assert not result.is_error, result.content
        assert result.structured_content

    def test_sizes_are_capped(self, explorer: Explorer) -> None:
        result = self.call(explorer, "thread", {"thread_id": "s1", "max_chars": 0})
        bodies = [row["body"] for row in result.structured_content["result"]]
        assert max(len(b) for b in bodies) <= 1

    @pytest.mark.parametrize(
        ("name", "args", "message"),
        [
            ("run_sql", {"query": "DELETE FROM comments"}, "Only SELECT"),
            ("user_profile", {"author": "alcie"}, "alice"),
            ("thread", {"thread_id": "nope"}, "No comments"),
        ],
    )
    def test_expected_errors_reach_the_model(
        self, explorer: Explorer, name: str, args: dict[str, Any], message: str
    ) -> None:
        # Regression: the SDK hides the text of arbitrary exceptions, so the
        # assistant could not see why a call failed.
        result = self.call(explorer, name, args)
        assert result.is_error
        assert message in result.content[0].text
