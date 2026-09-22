import numpy as np
import pytest
from shapely.geometry import MultiPolygon, Point, Polygon, box

from netsy.helpers.sampling import sample_points, truncated_draw


def _draw(levels, probabilities, budget, seed=0):
    return truncated_draw(np.array(levels), np.cumsum(probabilities), budget, np.random.default_rng(seed))


def test_draw_never_exceeds_the_budget():
    rng = np.random.default_rng(1)
    levels, cumulative = np.array([0, 2, 5, 9]), np.cumsum([0.25, 0.25, 0.25, 0.25])
    draws = {truncated_draw(levels, cumulative, 5, rng) for _ in range(500)}
    assert draws == {0, 2, 5}


def test_draw_renormalizes_over_the_feasible_levels():
    rng = np.random.default_rng(2)
    levels, cumulative = np.array([0, 5]), np.cumsum([0.2, 0.8])
    draws = [truncated_draw(levels, cumulative, 4, rng) for _ in range(50)]
    assert set(draws) == {0}


def test_draw_frequencies_follow_the_distribution():
    rng = np.random.default_rng(3)
    levels, cumulative = np.array([1, 2, 3]), np.cumsum([0.2, 0.3, 0.5])
    draws = np.array([truncated_draw(levels, cumulative, 10, rng) for _ in range(20000)])
    assert [(draws == level).mean() for level in (1, 2, 3)] == pytest.approx([0.2, 0.3, 0.5], abs=0.02)


def test_draw_is_none_when_no_level_is_feasible():
    assert _draw([5, 9], [0.5, 0.5], 4) is None


def test_draw_is_none_when_the_feasible_levels_have_no_probability():
    assert _draw([0, 5], [0.0, 1.0], 4) is None


def test_draw_skips_levels_with_zero_probability():
    rng = np.random.default_rng(4)
    levels, cumulative = np.array([0, 1, 2]), np.cumsum([0.0, 0.0, 1.0])
    assert {truncated_draw(levels, cumulative, 9, rng) for _ in range(50)} == {2}


def test_draw_is_a_plain_int():
    assert type(_draw([3], [1.0], 3)) is int


def test_points_are_inside_the_polygon_and_counted():
    polygon = Polygon([(0, 0), (4, 0), (0, 4)])
    x, y = sample_points(polygon, 500, np.random.default_rng(5))
    assert len(x) == len(y) == 500
    assert all(polygon.contains(Point(a, b)) for a, b in zip(x, y))


def test_points_cover_every_part_of_a_multipolygon():
    polygon = MultiPolygon([box(0, 0, 1, 1), box(10, 0, 11, 1)])
    x, _ = sample_points(polygon, 400, np.random.default_rng(6))
    assert (x < 5).any() and (x > 5).any()


def test_points_from_a_thin_polygon_still_arrive():
    polygon = Polygon([(0, 0), (100, 1), (100, 2)])
    x, y = sample_points(polygon, 20, np.random.default_rng(7))
    assert len(x) == 20


def test_points_are_repeatable_with_a_seed():
    polygon = box(0, 0, 1, 1)
    first = sample_points(polygon, 10, np.random.default_rng(8))
    second = sample_points(polygon, 10, np.random.default_rng(8))
    assert np.array_equal(first[0], second[0])


def test_a_polygon_without_area_is_rejected():
    with pytest.raises(ValueError, match="no area"):
        sample_points(Polygon([(0, 0), (1, 1), (2, 2)]), 1, np.random.default_rng(9))
