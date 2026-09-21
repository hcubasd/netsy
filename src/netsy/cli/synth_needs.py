from netsy.cli._combine import run_combiner
from netsy.synth.needs import needs


def run(force=False):
    return run_combiner(
        effects="need_effects.csv",
        thresholds="need_thresholds.csv",
        output="needs.csv",
        combine=needs,
        force=force,
    )
