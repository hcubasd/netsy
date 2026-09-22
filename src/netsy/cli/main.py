import argparse
import importlib

# command -> (module providing run(force, ...), help text). Modules are imported
# only when their command runs, so `netsy --help` stays fast.
SYNTH_COMMANDS = {
    "supply": ("netsy.cli.synth_supply", "supply_effects.csv + supply_thresholds.csv -> supply.csv"),
    "demand": ("netsy.cli.synth_demand", "demand_effects.csv + demand_thresholds.csv -> demand.csv"),
    "capacities": ("netsy.cli.synth_capacities", "capacity_effects.csv + capacity_thresholds.csv -> capacities.csv"),
    "needs": ("netsy.cli.synth_needs", "need_effects.csv + need_thresholds.csv -> needs.csv"),
    "agents": (
        "netsy.cli.synth_agents",
        "supply.csv + demand.csv + capacities.csv + needs.csv + zones.gpkg -> agents.gpkg",
    ),
}


def build_parser():
    parser = argparse.ArgumentParser(prog="netsy")
    groups = parser.add_subparsers(dest="group", required=True)
    synth = groups.add_parser("synth", help="synthesize a data file from the files it depends on")
    commands = synth.add_subparsers(dest="command", required=True)
    for name, (module, description) in SYNTH_COMMANDS.items():
        command = commands.add_parser(name, help=description, description=description)
        command.add_argument("--force", action="store_true", help="overwrite the output file if it already exists")
        if name == "agents":
            command.add_argument("--seed", type=int, help="seed the random draws, so the same inputs give the same agents")
        command.set_defaults(module=module)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    options = {"force": args.force}
    if hasattr(args, "seed"):
        options["seed"] = args.seed
    return importlib.import_module(args.module).run(**options)
