import itertools

import numpy as np
import pandas as pd
from scipy.special import expit

from netsy.helpers.validate import EFFECT_KEYS, OUTPUT_KEYS, check_effects, check_thresholds


def dimensions(effects):
    """The stratum dimensions of an effects table, in order of appearance."""
    return list(dict.fromkeys(effects["stratum"]))


def _linear_predictor(effects, resource, combos, dims):
    """beta for every stratum combination: the sum, over dimensions, of the
    effect of that combination's value. NaN where any of those effects is
    empty or absent -- the additive model is undefined there, not zero.
    """
    beta = pd.Series(0.0, index=combos.index)
    for dim in dims:
        effect = effects.loc[effects["stratum"] == dim].set_index("stratum_value")[resource]
        beta = beta + combos[dim].map(effect)
    return beta


def pmf_table(effects, thresholds):
    """The ordered-logit distribution of every resource in every stratum.

    One row per (stratum combination, resource, resource_level), long on
    resource and level because a full distribution needs several rows per
    combination. `probability` is P(level) under the cumulative-logit model
    P(Y <= level_k) = logistic(mu_k - beta), where beta is the combination's
    linear predictor and mu_k its resource's k-th threshold. A (combination,
    resource) pair whose beta is undefined has no rows.

    Only resources present in both `effects` (as a column) and `thresholds`
    (as a `resource` value) are used.
    """
    check_effects(effects)
    check_thresholds(thresholds)

    dims = dimensions(effects)
    values = [list(dict.fromkeys(effects.loc[effects["stratum"] == dim, "stratum_value"])) for dim in dims]
    combos = pd.DataFrame(list(itertools.product(*values)), columns=dims)
    resources = [c for c in effects.columns if c not in EFFECT_KEYS and c in set(thresholds["resource"])]

    blocks = []
    for position, resource in enumerate(resources):
        ladder = thresholds.loc[thresholds["resource"] == resource].sort_values("resource_level")
        levels = ladder["resource_level"].to_numpy()
        cutpoints = ladder["threshold"].to_numpy()[:-1]

        beta = _linear_predictor(effects, resource, combos, dims).to_numpy()
        defined = np.flatnonzero(~np.isnan(beta))
        if defined.size == 0:
            continue

        cumulative = expit(cutpoints[None, :] - beta[defined, None])
        edges = np.hstack([np.zeros((defined.size, 1)), cumulative, np.ones((defined.size, 1))])

        block = combos.iloc[np.repeat(defined, levels.size)].reset_index(drop=True)
        block["resource"] = resource
        block["resource_level"] = np.tile(levels, defined.size)
        block["probability"] = np.diff(edges, axis=1).ravel()
        block["_combo"] = np.repeat(defined, levels.size)
        block["_resource"] = position
        blocks.append(block)

    columns = dims + list(OUTPUT_KEYS)
    if not blocks:
        return pd.DataFrame(columns=columns)
    table = pd.concat(blocks, ignore_index=True)
    table = table.sort_values(["_combo", "_resource"], kind="stable")
    return table[columns].reset_index(drop=True)


def expected_table(effects, thresholds):
    """The rounded expected level of every resource in every stratum.

    One row per stratum combination, one column per resource. Resources are
    counted in whole units, so the expectation of the `pmf_table`
    distribution is rounded to an integer. A resource with no defined
    distribution for a combination is left empty rather than zero, since zero
    is itself a level; a combination with no defined resource has no row.
    """
    pmf = pmf_table(effects, thresholds)
    dims = dimensions(effects)
    pmf["expected"] = pmf["resource_level"] * pmf["probability"]
    expected = pmf.groupby(dims + ["resource"], sort=False, as_index=False)["expected"].sum()

    table = pmf[dims].drop_duplicates(ignore_index=True)
    for resource in dict.fromkeys(pmf["resource"]):
        column = expected.loc[expected["resource"] == resource, dims + ["expected"]]
        table = table.merge(column.rename(columns={"expected": resource}), on=dims, how="left")
        table[resource] = table[resource].round().astype("Int64")
    return table
