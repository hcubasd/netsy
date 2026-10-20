import os
import sys

import numpy as np

from netsy.cli._output import may_write
from netsy.helpers.files import read_facilities, read_shipments, read_table, read_zones
from netsy.helpers.skims import read_skims
from netsy.synth.tours import tours


def run(force=False, seed=None):
    outputs = ("tours.gpkg", "tour_shipments.csv")
    if not all(may_write(output, force) for output in outputs):
        return 1
    try:
        trips, parts = tours(
            read_zones("zones.gpkg"),
            read_facilities("facilities.gpkg") if os.path.exists("facilities.gpkg") else None,
            read_skims("skims.omx"),
            read_shipments("shipments.gpkg"),
            read_table("shipment_vehicles.csv"),
            read_table("tour_settings.csv"),
            read_table("end_tour_first.csv"),
            read_table("end_tour_later.csv"),
            rng=np.random.default_rng(seed),
        )
    except ValueError as error:
        print(error, file=sys.stderr)
        return 1
    trips.to_file("tours.gpkg", driver="GPKG")
    parts.to_csv("tour_shipments.csv", index=False)
    return 0
