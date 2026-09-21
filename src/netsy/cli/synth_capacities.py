from netsy.cli._combine import run_combiner
from netsy.synth.capacities import capacities


def run(force=False):
    return run_combiner(
        effects="capacity_effects.csv",
        thresholds="capacity_thresholds.csv",
        output="capacities.csv",
        combine=capacities,
        force=force,
    )
