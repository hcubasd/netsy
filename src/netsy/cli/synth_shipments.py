import os
import sys

import numpy as np

from netsy.cli._output import may_write
from netsy.helpers.files import read_agents, read_facilities, read_table, read_zones
from netsy.helpers.skims import read_skims
from netsy.synth.shipments import shipments

TABLES = (
    "production_rates.csv", "consumption_rates.csv", "shipment_totals.csv", "flow_types.csv",
    "distance_decay.csv", "shipment_sizes.csv", "shipment_vehicles.csv", "vehicle_choice.csv",
)
# Read only when present: facilities for flow types that use them, and the
# delivery tables, both or neither, to choose delivery windows.
OPTIONAL_TABLES = ("delivery_windows.csv", "delivery_choice.csv")


def run(force=False, seed=None):
    output = "shipments.gpkg"
    if not may_write(output, force):
        return 1
    try:
        tables = {path: read_table(path) for path in TABLES}
        optional = {path: read_table(path) if os.path.exists(path) else None for path in OPTIONAL_TABLES}
        table = shipments(
            read_zones("zones.gpkg"),
            read_agents("agents.gpkg"),
            read_facilities("facilities.gpkg") if os.path.exists("facilities.gpkg") else None,
            read_skims("skims.omx"),
            *tables.values(),
            *optional.values(),
            rng=np.random.default_rng(seed),
        )
    except ValueError as error:
        print(error, file=sys.stderr)
        return 1
    table.to_file(output, driver="GPKG")
    return 0
