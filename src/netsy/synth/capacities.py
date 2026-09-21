from netsy.helpers.ordered_logit import pmf_table


def capacities(effects, thresholds):
    """The capacity distribution of an individual agent: the probability of
    each resource level in each stratum combination, from the capacity
    effects and thresholds. Long on resource and level; agents are sampled
    from it later.
    """
    return pmf_table(effects, thresholds)
