from netsy.helpers.ordered_logit import expected_table


def demand(effects, thresholds):
    """Aggregate demand: the rounded expected level of each resource in each
    stratum combination, from the demand effects and thresholds. Wide, one
    column per resource.
    """
    return expected_table(effects, thresholds)
