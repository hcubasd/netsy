from netsy.cli._combine import run_combiner
from netsy.synth.demand import demand


def run(force=False):
    return run_combiner(
        effects="demand_effects.csv",
        thresholds="demand_thresholds.csv",
        output="demand.csv",
        combine=demand,
        force=force,
    )
