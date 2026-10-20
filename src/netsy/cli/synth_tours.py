import os
import sys

import numpy as np

from netsy.cli._output import may_write
from netsy.helpers.files import read_facilities, read_shipments, read_table, read_zones
from netsy.helpers.skims import read_skims
from netsy.synth.tours import tours


def run(force=False, seed=None, shipments="shipments.gpkg"):
    outputs = ("tours.gpkg", "tour_shipments.csv")
    if not all(may_write(output, force) for output in outputs):
        return 1
    try:
        trips, parts = tours(
            read_zones("zones.gpkg"),
            read_facilities("facilities.gpkg") if os.path.exists("facilities.gpkg") else None,
            read_skims("skims.omx"),
            read_shipments(shipments),
            read_table("shipment_vehicles.csv"),
            read_table("tour_settings.csv"),
            read_table("end_tour_first.csv"),
            read_table("end_tour_later.csv"),
            rng=np.random.default_rng(seed),
            combustion_shares=read_table("combustion_shares.csv") if os.path.exists("combustion_shares.csv") else None,
            combustion_zone_column=(read_table("combustion_settings.csv").set_index("setting").loc["zone_column", "value"]
                                    if os.path.exists("combustion_settings.csv") else None),
        )
    except ValueError as error:
        print(error, file=sys.stderr)
        return 1
    trips.to_file("tours.gpkg", driver="GPKG")
    parts.to_csv("tour_shipments.csv", index=False)
    return 0
