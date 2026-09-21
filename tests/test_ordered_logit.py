import numpy as np
import pandas as pd
import pytest

from netsy.helpers.ordered_logit import expected_table, pmf_table


def _pmf(table, zone_id, stratum_1, stratum_2, resource):
    rows = table[
        (table["zone_id"] == zone_id)
        & (table["stratum_1"] == stratum_1)
        & (table["stratum_2"] == stratum_2)
        & (table["resource"] == resource)
    ]
    return rows["probability"].tolist()


def test_pmf_matches_the_appendix_tables(effects, thresholds):
    table = pmf_table(effects, thresholds)
    assert _pmf(table, "2", "value_1", "value_1", "resource_1") == pytest.approx([0.443, 0.303, 0.254], abs=5e-4)
    assert _pmf(table, "2", "value_1", "value_1", "resource_2") == pytest.approx([0.272, 0.728], abs=5e-4)
    assert _pmf(table, "1", "value_2", "value_1", "resource_1") == pytest.approx([0.898, 0.072, 0.030], abs=5e-4)
    assert _pmf(table, "1", "value_2", "value_1", "resource_2") == pytest.approx([0.845, 0.155], abs=5e-4)


def test_pmf_is_a_distribution_per_combination_and_resource(effects, thresholds):
    table = pmf_table(effects, thresholds)
    totals = table.groupby(["zone_id", "stratum_1", "stratum_2", "resource"])["probability"].sum()
    assert len(totals) == 2 * 2 * 2 * 2
    assert totals.to_numpy() == pytest.approx(1.0)
    assert (table["probability"] >= 0).all()


def test_pmf_is_long_with_the_levels_of_each_resource(effects, thresholds):
    table = pmf_table(effects, thresholds)
    assert list(table.columns) == ["zone_id", "stratum_1", "stratum_2", "resource", "resource_level", "probability"]
    first = table.head(5)
    assert first["resource"].tolist() == ["resource_1"] * 3 + ["resource_2"] * 2
    assert first["resource_level"].tolist() == [0, 2, 3, 4, 9]
    assert len(table) == 8 * 5


def test_larger_predictor_moves_mass_to_higher_levels(effects, thresholds):
    table = pmf_table(effects, thresholds)
    low = _pmf(table, "1", "value_1", "value_2", "resource_1")
    high = _pmf(table, "2", "value_1", "value_1", "resource_1")
    assert high[-1] > low[-1]
    assert high[0] < low[0]


def test_unsorted_thresholds_file_order_does_not_matter(effects, thresholds):
    shuffled = thresholds.iloc[[4, 2, 1, 3, 0]].reset_index(drop=True)
    pd.testing.assert_frame_equal(pmf_table(effects, shuffled), pmf_table(effects, thresholds))


def test_empty_effect_omits_the_pair_not_the_combination(effects, thresholds):
    effects.loc[(effects["stratum"] == "stratum_1") & (effects["stratum_value"] == "value_2"), "resource_2"] = np.nan
    table = pmf_table(effects, thresholds)
    omitted = table[(table["stratum_1"] == "value_2") & (table["resource"] == "resource_2")]
    assert omitted.empty
    kept = table[(table["stratum_1"] == "value_2") & (table["resource"] == "resource_1")]
    assert not kept.empty


def test_resource_missing_from_either_file_is_dropped(effects, thresholds):
    only_first = thresholds[thresholds["resource"] == "resource_1"]
    assert set(pmf_table(effects, only_first)["resource"]) == {"resource_1"}
    without_effect = effects.drop(columns="resource_2")
    assert set(pmf_table(without_effect, thresholds)["resource"]) == {"resource_1"}


def test_single_level_resource_has_probability_one(effects):
    thresholds = pd.DataFrame({"resource": ["resource_1"], "resource_level": [7], "threshold": [np.nan]})
    table = pmf_table(effects, thresholds)
    assert table["resource_level"].eq(7).all()
    assert table["probability"].eq(1.0).all()


def test_no_shared_resource_gives_an_empty_table(effects):
    thresholds = pd.DataFrame({"resource": ["other"], "resource_level": [0], "threshold": [np.nan]})
    table = pmf_table(effects, thresholds)
    assert table.empty
    assert list(table.columns) == ["zone_id", "stratum_1", "stratum_2", "resource", "resource_level", "probability"]


def test_extreme_effects_do_not_overflow(effects, thresholds):
    effects["resource_1"] = 1e4
    table = pmf_table(effects, thresholds)
    assert table["probability"].notna().all()


def test_expected_table_matches_the_appendix_supply_table(effects, thresholds):
    table = expected_table(effects, thresholds)
    assert list(table.columns) == ["zone_id", "stratum_1", "stratum_2", "resource_1", "resource_2"]
    assert table[["zone_id", "stratum_1", "stratum_2"]].values.tolist() == [
        ["1", "value_1", "value_1"], ["1", "value_1", "value_2"],
        ["1", "value_2", "value_1"], ["1", "value_2", "value_2"],
        ["2", "value_1", "value_1"], ["2", "value_1", "value_2"],
        ["2", "value_2", "value_1"], ["2", "value_2", "value_2"],
    ]
    assert table["resource_1"].tolist() == [0, 0, 0, 0, 1, 0, 2, 0]
    assert table["resource_2"].tolist() == [5, 7, 5, 6, 8, 9, 7, 9]


def test_expected_values_are_whole_units(effects, thresholds):
    table = expected_table(effects, thresholds)
    assert str(table["resource_1"].dtype) == "Int64"


def test_expected_table_leaves_undefined_pairs_empty_not_zero(effects, thresholds):
    effects.loc[(effects["stratum"] == "zone_id") & (effects["stratum_value"] == "2"), "resource_2"] = np.nan
    table = expected_table(effects, thresholds)
    zone_2 = table[table["zone_id"] == "2"]
    assert zone_2["resource_2"].isna().all()
    assert zone_2["resource_1"].notna().all()
    assert (table[table["zone_id"] == "1"]["resource_1"] == 0).all()


def test_combination_without_any_defined_resource_has_no_row(effects, thresholds):
    effects.loc[(effects["stratum"] == "zone_id") & (effects["stratum_value"] == "2"), ["resource_1", "resource_2"]] = np.nan
    table = expected_table(effects, thresholds)
    assert set(table["zone_id"]) == {"1"}
