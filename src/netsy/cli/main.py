import argparse
import importlib

# command -> (module providing run(force, ...), help text). Modules are imported
# only when their command runs, so `netsy --help` stays fast.
SYNTH_COMMANDS = {
    "agents": (
        "netsy.cli.synth_agents",
        "zones.gpkg + size_totals.csv + size_classes.csv -> agents.gpkg",
    ),
    "shipments": (
        "netsy.cli.synth_shipments",
        "zones.gpkg + agents.gpkg + skims.omx + shipment CSVs -> shipments.gpkg",
    ),
    "facility-chains": (
        "netsy.cli.synth_facility_chains",
        "shipments.gpkg + facilities.gpkg + facility_chain_steps.csv -> transaction_legs.gpkg",
    ),
    "od-flows": (
        "netsy.cli.synth_od_flows",
        "productions.csv + attractions.csv + od_prior.csv -> od_flows.csv",
    ),
    "network-loads": (
        "netsy.cli.synth_network_loads",
        "network.gpkg + transaction lines + supporting CSVs -> network_loads.csv",
    ),
    "network-emissions": (
        "netsy.cli.synth_network_emissions",
        "network_loads.csv + COPERT V inputs -> network_emissions.csv",
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
        if name in {"agents", "shipments", "network-loads"}:
            command.add_argument("--seed", type=int, help="seed the random draws, so the same inputs give the same output")
        if name == "agents":
            command.add_argument(
                "--min-size",
                type=float,
                default=0,
                metavar="SIZE",
                help="drop agents smaller than SIZE once drawn; their size is not given to others",
            )
        if name == "network-loads":
            command.add_argument(
                "--transactions",
                metavar="PATH",
                help="transaction-line GeoPackage; defaults to shipments.gpkg",
            )
        command.set_defaults(module=module)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    options = {"force": args.force}
    if hasattr(args, "seed"):
        options["seed"] = args.seed
    if hasattr(args, "min_size"):
        options["min_size"] = args.min_size
    if hasattr(args, "transactions"):
        options["transactions"] = args.transactions
    return importlib.import_module(args.module).run(**options)
