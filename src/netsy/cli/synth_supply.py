from netsy.cli._combine import run_combiner
from netsy.synth.supply import supply


def run(force=False):
    return run_combiner(
        effects="supply_effects.csv",
        thresholds="supply_thresholds.csv",
        output="supply.csv",
        combine=supply,
        force=force,
    )
