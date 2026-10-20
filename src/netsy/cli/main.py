import argparse
import importlib

# command -> (module providing run(force, ...), help text). Modules are imported
# only when their command runs, so `netsy --help` stays fast.
SYNTH_COMMANDS = {
    "indicators": ("netsy.cli.synth_indicators", "model outputs + optional groupings -> indicators.csv"),
    "parcel-routing": ("netsy.cli.synth_parcel_routing", "parcel demand + facility rules -> routed_parcel_demand.csv"),
    "facility-routing": ("netsy.cli.synth_facility_routing", "shipments + zone rules -> routed_shipments.gpkg"),
    "agents": (
        "netsy.cli.synth_agents",
        "zones.gpkg + size_totals.csv + size_classes.csv -> agents.gpkg",
    ),
    "shipments": (
        "netsy.cli.synth_shipments",
        "zones.gpkg + agents.gpkg + skims.omx + shipment CSVs -> shipments.gpkg",
    ),
    "tours": (
        "netsy.cli.synth_tours",
        "shipments.gpkg + zones.gpkg + skims.omx + tour CSVs -> tours.gpkg + tour_shipments.csv",
    ),
    "parcel-demand": (
        "netsy.cli.synth_parcel_demand",
        "zones.gpkg + facilities.gpkg + skims.omx + parcel CSVs -> parcel_demand.csv",
    ),
    "deliveries": (
        "netsy.cli.synth_deliveries",
        "parcel_demand.csv + zones.gpkg + skims.omx + delivery CSVs -> delivery_tours.gpkg",
    ),
    "trip-matrices": (
        "netsy.cli.synth_trip_matrices",
        "zones.gpkg + skims.omx + trip CSVs -> trip_matrices.omx",
    ),
    "facility-chains": (
        "netsy.cli.synth_facility_chains",
        "shipments.gpkg + facilities.gpkg + facility_chain_steps.csv -> transaction_legs.gpkg",
    ),
    "od-marginals": (
        "netsy.cli.synth_od_marginals",
        "location_attributes.csv + marginal_coefficients.csv + od_prior.csv -> productions.csv + attractions.csv",
    ),
    "od-flows": (
        "netsy.cli.synth_od_flows",
        "productions.csv + attractions.csv + od_prior.csv -> od_flows.csv",
    ),
    "network-loads": (
        "netsy.cli.synth_network_loads",
        "network.gpkg + zones.gpkg + trips + assignment CSVs -> network_loads.parquet",
    ),
    "network-emissions": (
        "netsy.cli.synth_network_emissions",
        "network_loads.parquet + network.gpkg + emission factors or COPERT V inputs -> network_emissions.parquet",
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
        if name in {"agents", "shipments", "tours", "deliveries", "facility-routing", "parcel-routing"}:
            command.add_argument("--seed", type=int, help="seed the random draws, so the same inputs give the same output")
        if name == "tours":
            command.add_argument("--shipments", default="shipments.gpkg", help="shipment inputs, including routed_shipments.gpkg")
        if name == "agents":
            command.add_argument(
                "--min-size",
                type=float,
                default=0,
                metavar="SIZE",
                help="drop agents smaller than SIZE once drawn; their size is not given to others",
            )
        if name == "deliveries":
            command.add_argument("--demand", default="parcel_demand.csv")
            command.add_argument(
                "--routing",
                choices=("massgt", "savings"),
                default="massgt",
                help="MASS-GT's parcel clusters and stop order, or Clarke-Wright savings routes (default: massgt)",
            )
        if name == "network-loads":
            command.add_argument("--payload-strata", action="store_true", help="retain separate COPERT payload bins for nonlinear emission factors")
        if name == "network-emissions":
            command.add_argument(
                "--method",
                choices=("factors", "copert"),
                default="factors",
                help="MASS-GT's empty and full emission factors, or COPERT V (default: factors)",
            )
        command.set_defaults(module=module)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    options = {"force": args.force}
    if hasattr(args, "seed"):
        options["seed"] = args.seed
    if hasattr(args, "payload_strata"):
        options["payload_strata"] = args.payload_strata
    if hasattr(args, "demand"):
        options["demand"] = args.demand
    if hasattr(args, "shipments"):
        options["shipments"] = args.shipments
    if hasattr(args, "min_size"):
        options["min_size"] = args.min_size
    if hasattr(args, "method"):
        options["method"] = args.method
    if hasattr(args, "routing"):
        options["routing"] = args.routing
    return importlib.import_module(args.module).run(**options)
