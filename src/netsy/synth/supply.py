from netsy.helpers.ordered_logit import expected_table


def supply(effects, thresholds):
    """Aggregate supply: the rounded expected level of each resource in each
    stratum combination, from the supply effects and thresholds. Wide, one
    column per resource.
    """
    return expected_table(effects, thresholds)
