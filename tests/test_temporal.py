"""Tests for subreddit_lens.temporal."""

import numpy as np
import pandas as pd
import pytest

from subreddit_lens.temporal import (
    compute_posting_habits_pdf,
    js_distance_matrix,
    js_similarity,
    local_hour,
)

GRID = np.linspace(0, 24, 1001)


class TestLocalHour:
    def test_summer_time_in_rome(self) -> None:
        # Regression: hours used to be taken in UTC. 22:30 UTC in July is
        # 00:30 in Rome (CEST, UTC+2).
        ts = pd.Series([pd.Timestamp("2024-07-01 22:30", tz="UTC").timestamp()])
        assert local_hour(ts, tz="Europe/Rome").iloc[0] == pytest.approx(0.5)

    def test_winter_time_in_rome(self) -> None:
        ts = pd.Series([pd.Timestamp("2024-01-15 22:30", tz="UTC").timestamp()])
        assert local_hour(ts, tz="Europe/Rome").iloc[0] == pytest.approx(23.5)

    def test_default_is_utc(self) -> None:
        ts = pd.Series([pd.Timestamp("2024-07-01 13:45", tz="UTC").timestamp()])
        assert local_hour(ts).iloc[0] == pytest.approx(13.75)


def habits_df(posts: dict[str, list[float]]) -> pd.DataFrame:
    """Build a DataFrame of posts at the given UTC hours on 2024-01-01."""
    day = pd.Timestamp("2024-01-01", tz="UTC").timestamp()
    rows = [(author, day + h * 3600) for author, hours in posts.items() for h in hours]
    return pd.DataFrame(rows, columns=["author", "created_utc"])


class TestPostingHabitsPdf:
    def test_densities_integrate_to_one(self) -> None:
        df = habits_df({"a": [8, 9, 10, 20], "b": [1, 23, 23.5]})
        densities = compute_posting_habits_pdf(df, None, GRID)
        for density in densities.values():
            assert np.trapezoid(density, GRID) == pytest.approx(1.0)

    def test_density_wraps_around_midnight(self) -> None:
        df = habits_df({"night": [23.5, 0.5, 23.75, 0.25]})
        density = compute_posting_habits_pdf(df, None, GRID)["night"]
        assert density[0] == pytest.approx(density[-1])
        assert density[0] > density[len(GRID) // 2]

    def test_timezone_shifts_the_peak(self) -> None:
        df = habits_df({"a": [10, 10.1, 9.9, 10.05]})
        utc = compute_posting_habits_pdf(df, None, GRID)["a"]
        rome = compute_posting_habits_pdf(df, None, GRID, tz="Europe/Rome")["a"]
        assert GRID[np.argmax(utc)] == pytest.approx(10, abs=0.2)
        assert GRID[np.argmax(rome)] == pytest.approx(11, abs=0.2)  # CET, UTC+1

    def test_min_posts_and_author_list(self) -> None:
        df = habits_df({"a": [1, 2, 3], "b": [4, 5], "c": [6]})
        assert set(compute_posting_habits_pdf(df, None, GRID)) == {"a", "b"}
        assert set(compute_posting_habits_pdf(df, None, GRID, min_posts=3)) == {"a"}
        only_b = compute_posting_habits_pdf(df, ["b", "c", "unknown"], GRID)
        assert set(only_b) == {"b"}

    def test_excluded_authors(self) -> None:
        df = habits_df({"a": [1, 2], "AutoModerator": [3, 4], "[deleted]": [5, 6]})
        assert set(compute_posting_habits_pdf(df, None, GRID)) == {"a"}
        all_authors = compute_posting_habits_pdf(df, None, GRID, exclude_authors=None)
        assert len(all_authors) == 3

    def test_min_posts_below_two_raises(self) -> None:
        with pytest.raises(ValueError):
            compute_posting_habits_pdf(habits_df({"a": [1]}), None, GRID, min_posts=1)


class TestJensenShannon:
    def test_identical_and_disjoint_distributions(self) -> None:
        densities = {
            "a": np.array([1.0, 0.0]),
            "b": np.array([1.0, 0.0]),
            "c": np.array([0.0, 1.0]),
        }
        distances = js_distance_matrix(densities)
        assert distances[0, 1] == pytest.approx(0.0)
        # Regression: with the natural log the maximum was sqrt(ln 2) ~ 0.83.
        assert distances[0, 2] == pytest.approx(1.0)
        np.testing.assert_allclose(js_similarity(densities), 1 - distances)

    def test_matrix_properties(self) -> None:
        rng = np.random.default_rng(0)
        densities = {str(i): rng.random(50) for i in range(6)}
        distances = js_distance_matrix(densities)
        np.testing.assert_allclose(distances, distances.T)
        np.testing.assert_allclose(np.diag(distances), 0.0)
        assert distances.min() >= 0.0
        assert distances.max() <= 1.0
