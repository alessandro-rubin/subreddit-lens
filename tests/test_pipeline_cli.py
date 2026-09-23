"""Tests for subreddit_lens.pipeline and the command-line interface."""

import json
from pathlib import Path

import pandas as pd
import pytest
import zstandard as zstd
from typer.testing import CliRunner

from subreddit_lens import pipeline
from subreddit_lens.cli import app
from subreddit_lens.config import Config, load_config
from subreddit_lens.network import load_graph

runner = CliRunner()


def write_archive(path: Path, df: pd.DataFrame) -> None:
    payload = "\n".join(
        json.dumps(r, ensure_ascii=False) for r in df.to_dict("records")
    )
    path.write_bytes(zstd.ZstdCompressor().compress(payload.encode("utf-8")))


@pytest.fixture
def project(
    tmp_path: Path, comments_df: pd.DataFrame, submissions_df: pd.DataFrame
) -> Path:
    """A project directory with a config file and both archives."""
    (tmp_path / "data").mkdir()
    write_archive(tmp_path / "data" / "demo_comments.zst", comments_df)
    write_archive(tmp_path / "data" / "demo_submissions.zst", submissions_df)
    (tmp_path / "subreddit-lens.toml").write_text(
        'subreddit = "demo"\ntimezone = "Europe/Rome"\n', encoding="utf-8"
    )
    return tmp_path


@pytest.fixture
def config(project: Path) -> Config:
    return load_config(project / "subreddit-lens.toml")


def invoke(project: Path, *args: str) -> tuple[int, str]:
    result = runner.invoke(
        app, [*args[:1], "--config", str(project / "subreddit-lens.toml"), *args[1:]]
    )
    return result.exit_code, result.output


class TestPipeline:
    def test_full_run(self, config: Config) -> None:
        result = pipeline.run_ingest(config)
        assert result.comments == 11
        assert result.submissions == 2

        graph = load_graph(pipeline.run_network(config))
        # With submissions, alice's top-level reply to dave's post counts.
        assert graph.has_edge("alice", "dave")
        assert "AutoModerator" not in graph

        metrics = pd.read_csv(pipeline.run_metrics(config), index_col="author")
        assert set(metrics.index) == {"alice", "bob", "carol", "dave"}

        habits = pd.read_parquet(
            pipeline.run_habits(config, min_posts=2, resolution_minutes=30)
        )
        assert habits.index.name == "author"
        assert list(habits.columns[:3]) == ["n_posts", "00:00", "00:30"]
        assert habits.shape[1] == 1 + 48
        assert habits.loc["alice", "n_posts"] == 4

        paths = pipeline.run_export(config)
        assert paths == [config.chains_file, config.pairs_file]
        pairs = config.pairs_file.read_text(encoding="utf-8").splitlines()
        assert len(pairs) == 7

    def test_ingest_without_submissions(self, config: Config) -> None:
        config.submissions_archive.unlink()
        result = pipeline.run_ingest(config)
        assert result.submissions is None
        assert not config.submissions_parquet.exists()

    def test_steps_require_their_inputs(self, config: Config) -> None:
        with pytest.raises(FileNotFoundError, match="ingest"):
            pipeline.run_network(config)
        with pytest.raises(FileNotFoundError, match="network"):
            pipeline.run_metrics(config)
        config.comments_archive.unlink()
        with pytest.raises(FileNotFoundError, match="comments dump"):
            pipeline.run_ingest(config)

    def test_export_clean_text(self, config: Config) -> None:
        pipeline.run_ingest(config)
        pipeline.run_export(config, chains=False, clean_text=True)
        pairs = [
            json.loads(line)
            for line in config.pairs_file.read_text(encoding="utf-8").splitlines()
        ]
        texts = {p["assistant"] for p in pairs}
        # c2 is a quote of c1 followed by a reply: only the reply is kept.
        assert "Non sono d'accordo" in texts
        # c3 contains a Markdown link: only the display text is kept.
        assert "Vedi qui" in texts
        assert not config.chains_file.exists()

    def test_invalid_habits_resolution(self, config: Config) -> None:
        with pytest.raises(ValueError):
            pipeline.run_habits(config, resolution_minutes=7)


class TestCli:
    def test_commands_end_to_end(self, project: Path) -> None:
        for command in ["ingest", "network", "metrics", "habits", "export"]:
            code, output = invoke(project, command)
            assert code == 0, output
        assert (project / "output" / "demo_user_metrics.csv").exists()
        assert (project / "output" / "demo_pairs.jsonl").exists()

    def test_run(self, project: Path) -> None:
        code, output = invoke(project, "run")
        assert code == 0, output
        for step in ["[ingest]", "[network]", "[metrics]", "[habits]", "[export]"]:
            assert step in output
        code, output = invoke(project, "run", "--skip-ingest")
        assert code == 0, output
        assert "[ingest]" not in output

    def test_missing_input_is_a_clean_error(self, project: Path) -> None:
        code, output = invoke(project, "network")
        assert code == 1
        assert "Run the ingest step first" in output
        assert "Traceback" not in output

    def test_missing_config(self, tmp_path: Path) -> None:
        result = runner.invoke(
            app, ["network", "--config", str(tmp_path / "none.toml")]
        )
        assert result.exit_code == 1
        assert "subreddit-lens init" in result.output

    def test_overrides(self, project: Path) -> None:
        code, output = invoke(project, "ingest", "--start", "2030-01-01")
        assert code == 0, output
        assert "0 comments" in output  # every fixture comment is older
        code, output = invoke(project, "ingest", "--start", "yesterday")
        assert code == 1
        assert "YYYY-MM-DD" in output

        other = project / "elsewhere"
        code, output = invoke(project, "ingest")
        assert code == 0, output
        code, output = invoke(project, "export", "--output-dir", str(other))
        assert code == 0, output
        assert (other / "demo_threads.jsonl").exists()

    def test_export_format(self, project: Path) -> None:
        invoke(project, "ingest")
        code, output = invoke(project, "export", "--format", "pairs")
        assert code == 0, output
        assert (project / "output" / "demo_pairs.jsonl").exists()
        assert not (project / "output" / "demo_threads.jsonl").exists()

    def test_init(self, tmp_path: Path) -> None:
        path = tmp_path / "conf" / "subreddit-lens.toml"
        args = ["init", "litigi", "--config", str(path), "--timezone", "Europe/Rome"]
        result = runner.invoke(app, args)
        assert result.exit_code == 0, result.output
        config = load_config(path)
        assert config.subreddit == "litigi"
        assert config.timezone == "Europe/Rome"
        assert config.data_dir == (tmp_path / "conf" / "data").resolve()

        again = runner.invoke(app, args)
        assert again.exit_code == 1
        assert "--force" in again.output
        assert runner.invoke(app, [*args, "--force"]).exit_code == 0

    def test_init_rejects_invalid_values(self, tmp_path: Path) -> None:
        result = runner.invoke(
            app,
            ["init", "r/litigi", "--config", str(tmp_path / "c.toml")],
        )
        assert result.exit_code == 1
        assert not (tmp_path / "c.toml").exists()

    def test_verbose_flag(self, project: Path) -> None:
        result = runner.invoke(
            app,
            ["-v", "ingest", "--config", str(project / "subreddit-lens.toml")],
        )
        assert result.exit_code == 0, result.output
