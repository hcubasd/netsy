import numpy as np
import pandas as pd
import pytest

from netsy.helpers.ordered_logit import pmf_table
from netsy.helpers.validate import check_effects, check_thresholds


def test_valid_tables_pass(effects, thresholds):
    check_effects(effects)
    check_thresholds(thresholds)


@pytest.mark.parametrize("column", ["stratum", "stratum_value"])
def test_effects_need_the_key_columns(effects, column):
    with pytest.raises(ValueError, match=column):
        check_effects(effects.drop(columns=column))


def test_effects_need_a_resource_column(effects):
    with pytest.raises(ValueError, match="resource column"):
        check_effects(effects[["stratum", "stratum_value"]])


def test_effects_need_zone_id(effects):
    with pytest.raises(ValueError, match="zone_id"):
        check_effects(effects[effects["stratum"] != "zone_id"])


def test_effects_reject_duplicate_pairs(effects):
    with pytest.raises(ValueError, match="duplicate"):
        check_effects(pd.concat([effects, effects.head(1)], ignore_index=True))


def test_effects_reject_a_stratum_named_like_a_resource(effects):
    effects.loc[effects["stratum"] == "stratum_1", "stratum"] = "resource_1"
    with pytest.raises(ValueError, match="clash"):
        check_effects(effects)


def test_effects_reject_non_numeric_resource_column(effects):
    effects["resource_1"] = effects["resource_1"].astype(str)
    with pytest.raises(ValueError, match="numeric"):
        check_effects(effects)


def test_effects_reject_empty_keys(effects):
    effects.loc[0, "stratum_value"] = np.nan
    with pytest.raises(ValueError, match="empty"):
        check_effects(effects)


def test_thresholds_need_exactly_the_three_columns(thresholds):
    with pytest.raises(ValueError, match="exactly"):
        check_thresholds(thresholds.assign(extra=1))


def test_thresholds_need_integer_levels(thresholds):
    thresholds["resource_level"] = thresholds["resource_level"].astype(float) + 0.5
    with pytest.raises(ValueError, match="integers"):
        check_thresholds(thresholds)


def test_thresholds_reject_repeated_levels(thresholds):
    thresholds.loc[1, "resource_level"] = 0
    with pytest.raises(ValueError, match="distinct"):
        check_thresholds(thresholds)


def test_thresholds_reject_a_threshold_on_the_largest_level(thresholds):
    thresholds.loc[2, "threshold"] = 3.0
    with pytest.raises(ValueError, match="largest"):
        check_thresholds(thresholds)


def test_thresholds_reject_a_missing_threshold_below_the_largest_level(thresholds):
    thresholds.loc[0, "threshold"] = np.nan
    with pytest.raises(ValueError, match="largest"):
        check_thresholds(thresholds)


def test_thresholds_reject_unsorted_cutpoints(thresholds):
    thresholds.loc[0, "threshold"] = 5.0
    with pytest.raises(ValueError, match="sorted"):
        check_thresholds(thresholds)


def test_the_model_validates_its_inputs(effects, thresholds):
    thresholds.loc[0, "threshold"] = 5.0
    with pytest.raises(ValueError, match="sorted"):
        pmf_table(effects, thresholds)
