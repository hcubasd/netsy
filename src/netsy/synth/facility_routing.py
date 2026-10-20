"""Route shipments through facilities serving flagged zones, as MASS-GT's
urban consolidation centre (UCC) scenario does, generalized to any zone
flag, facility assignment and strata.

A shipment with one end in a flagged zone goes, with its stratum's
probability, through the facility that serves that zone: it becomes the
original shipment, now ending (or starting) at the facility, and a new leg
between the facility and the zone, by a vehicle drawn from its stratum's
shares. A shipment with both ends in flagged zones of one area only takes
a new vehicle; one between areas becomes three legs, through both zones'
facilities. A leg between a facility and a flagged zone is carried by the
facility's carrier, the leg out of a facility winning over the one in. A
stratum without vehicle shares keeps its vehicle.
"""

import geopandas
import numpy as np
import pandas as pd
from shapely.geometry import LineString

from netsy.helpers.geometry import zone_points
from netsy.synth.agents import _zone_key
from netsy.synth.shipments import _rows_for

SETTINGS = ("zone_column", "facility_column", "area_column")


def _settings(table):
    if not {"setting", "value"} <= set(table) or table.setting.duplicated().any():
        raise ValueError("routing_settings.csv: unique setting/value rows are required")
    values = dict(zip(table["setting"], table["value"]))
    missing = [name for name in SETTINGS if name not in values]
    if missing:
        raise ValueError(f"routing_settings.csv: missing settings {missing}")
    unknown = sorted(set(values) - set(SETTINGS))
    if unknown:
        raise ValueError(f"routing_settings.csv: unknown settings {unknown}; settings are {list(SETTINGS)}")
    return values


class _Draws:
    """Per stratum: the probability of routing through a facility and the
    cumulative vehicle shares of the new legs.
    """

    def __init__(self, probabilities, vehicles, strata):
        for table, required, name in ((probabilities, {"probability"}, "routing_probabilities.csv"), (vehicles, {"vehicle", "share"}, "routing_vehicles.csv")):
            if required - set(table): raise ValueError(f"{name}: missing columns {sorted(required-set(table))}")
        self.probabilities, self.vehicles = probabilities, vehicles
        self.probability_keys = [c for c in probabilities.columns if c != "probability"]
        self.vehicle_keys = [c for c in vehicles.columns if c not in ("vehicle", "share")]
        for name, keys in (("routing_probabilities.csv", self.probability_keys), ("routing_vehicles.csv", self.vehicle_keys)):
            extra = sorted(set(keys) - set(strata))
            if extra:
                raise ValueError(f"{name}: columns {extra} are not stratum columns of shipments.gpkg")
        for table, column in ((probabilities, "probability"), (vehicles, "share")):
            numbers = pd.to_numeric(table[column], errors="coerce")
            if not np.isfinite(numbers).all() or (numbers < 0).any() or (column == "probability" and (numbers > 1).any()):
                raise ValueError(f"routing {column}: invalid probabilities or shares")
        duplicate_rules = probabilities.duplicated(self.probability_keys).any() if self.probability_keys else len(probabilities) > 1
        if duplicate_rules:
            raise ValueError("routing_probabilities.csv: duplicate stratum rules")
        self.cache = {}

    def of(self, stratum):
        key = tuple(sorted(stratum.items()))
        if key not in self.cache:
            rows = _rows_for(self.probabilities, self.probability_keys, stratum)
            probability = float(pd.to_numeric(rows["probability"]).iloc[0]) if len(rows) else 0.0
            rows = _rows_for(self.vehicles, self.vehicle_keys, stratum)
            shares = pd.to_numeric(rows["share"]).to_numpy(float)
            vehicles = rows["vehicle"].map(_zone_key).to_numpy()
            self.cache[key] = (probability, vehicles, np.cumsum(shares) / shares.sum() if shares.sum() > 0 else None)
        return self.cache[key]


def facility_routing(shipments, zones, facilities, settings, probabilities, vehicles, rng):
    """The shipments with those routed through facilities split into legs,
    and the columns `leg` (the shipment's legs in order), `carrier` (the
    facility carrying a leg between it and a flagged zone, else empty) and
    `routed` (whether the shipment was rerouted). Raises ValueError if the
    tables do not fit together.
    """
    required = {"transaction_id", "resource", "quantity", "vehicle", "origin_zone_id", "destination_zone_id"}
    if required - set(shipments):
        raise ValueError(f"shipments.gpkg: missing columns {sorted(required-set(shipments))}")
    quantities = pd.to_numeric(shipments.quantity, errors="coerce")
    if not np.isfinite(quantities).all() or (quantities <= 0).any():
        raise ValueError("shipments.gpkg: quantities must be finite and positive")
    if shipments.transaction_id.duplicated().any():
        raise ValueError("shipments.gpkg: transaction_id must be unique before routing")
    if shipments.crs != zones.crs or shipments.crs != facilities.crs:
        raise ValueError("shipments, zones and facilities must share a CRS")
    if zones.zone_id.duplicated().any():
        raise ValueError("zones.gpkg: zone_id must be unique")
    if facilities.facility_id.duplicated().any():
        raise ValueError("facilities.gpkg: facility_id must be unique")
    values = _settings(settings)
    for column in (values["zone_column"], values["facility_column"], values["area_column"]):
        if column not in zones.columns:
            raise ValueError(f"zones.gpkg: missing column {column!r}")
    keys = zones["zone_id"].map(_zone_key)
    original_zone_ids = dict(zip(keys, zones["zone_id"]))
    flagged = dict(zip(keys, pd.to_numeric(zones[values["zone_column"]], errors="coerce").fillna(0) >= 1))
    serving = dict(zip(keys, zones[values["facility_column"]].map(lambda v: None if pd.isna(v) else _zone_key(v))))
    area = dict(zip(keys, zones[values["area_column"]].map(lambda v: None if pd.isna(v) else _zone_key(v))))
    facility_zone = dict(zip(facilities["facility_id"].map(_zone_key), facilities["zone_id"].map(_zone_key)))
    for zone, facility in serving.items():
        if flagged[zone] and facility not in facility_zone:
            raise ValueError(f"zones.gpkg: flagged zone {zone!r} needs a facility of facilities.gpkg in {values['facility_column']!r}")
    point_of = dict(zip(keys, map(tuple, zone_points(zones))))
    known = set(keys)
    if not set(shipments.origin_zone_id.map(_zone_key)).issubset(known) or not set(shipments.destination_zone_id.map(_zone_key)).issubset(known):
        raise ValueError("shipments.gpkg: every endpoint zone must exist")

    reserved = {
        "transaction_id", "quantity", "origin_agent_id", "destination_agent_id", "flow_type", "origin_facility_id",
        "destination_facility_id", "origin_zone_id", "destination_zone_id", "size_class", "vehicle", "window",
        "window_start", "window_end", "geometry", "carrier", "combustion", "leg", "routed", "parent_transaction_id",
    }
    strata = [column for column in shipments.columns if column not in reserved]
    draws = _Draws(probabilities, vehicles, strata)
    rows = shipments.drop(columns="geometry").to_dict("records")
    output = []

    def leg(row, number, origin=None, destination=None, vehicle=None):
        new = dict(row, leg=number, routed=True, _from=origin, _to=destination)
        for side, facility in (("origin", origin), ("destination", destination)):
            if facility is not None:
                new[f"{side}_facility_id"] = facility
                new[f"{side}_agent_id"] = None
                new[f"{side}_zone_id"] = original_zone_ids[facility_zone[facility]]
        if vehicle is not None:
            new["vehicle"] = vehicle
        return new

    for row in rows:
        origin, destination = _zone_key(row["origin_zone_id"]), _zone_key(row["destination_zone_id"])
        stratum = {column: _zone_key(row[column]) for column in strata}
        probability, choices, cumulative = draws.of(stratum)

        def vehicle():
            return choices[min(np.searchsorted(cumulative, rng.random(), side="right"), len(choices) - 1)]

        in_origin, in_destination = flagged.get(origin, False), flagged.get(destination, False)
        if in_origin and in_destination:
            if area[origin] == area[destination]:
                output.append(dict(row, leg=1, routed=False, _from=None, _to=None, vehicle=vehicle() if cumulative is not None else row["vehicle"]))
            elif rng.random() < probability:
                first, second = serving[origin], serving[destination]
                output.append(leg(row, 1, destination=first, vehicle=vehicle() if cumulative is not None else None))
                output.append(leg(row, 2, origin=first, destination=second))
                output.append(leg(row, 3, origin=second, vehicle=vehicle() if cumulative is not None else None))
            else:
                output.append(dict(row, leg=1, routed=False, _from=None, _to=None))
        elif in_origin and rng.random() < probability:
            facility = serving[origin]
            output.append(leg(row, 1, destination=facility, vehicle=vehicle() if cumulative is not None else None))
            output.append(leg(row, 2, origin=facility))
        elif in_destination and rng.random() < probability:
            facility = serving[destination]
            output.append(leg(row, 1, destination=facility))
            output.append(leg(row, 2, origin=facility, vehicle=vehicle() if cumulative is not None else None))
        else:
            output.append(dict(row, leg=1, routed=False, _from=None, _to=None))

    # A leg into a facility from a flagged zone, or out of one into a flagged
    # zone, is the facility's to carry (the second rule winning, as in MASS-GT).
    for row in output:
        carrier = None
        if row["_to"] is not None and flagged.get(_zone_key(row["origin_zone_id"]), False):
            carrier = row["_to"]
        if row["_from"] is not None and flagged.get(_zone_key(row["destination_zone_id"]), False):
            carrier = row["_from"]
        row["carrier"] = carrier
        del row["_from"], row["_to"]
    table = pd.DataFrame(output)
    table["parent_transaction_id"] = table["transaction_id"]
    table["transaction_id"] = range(1, len(table)+1)
    lines = [
        LineString([point_of[_zone_key(o)], point_of[_zone_key(d)]])
        for o, d in zip(table["origin_zone_id"], table["destination_zone_id"])
    ]
    for side in ("origin", "destination"):
        if f"{side}_agent_id" in table.columns and pd.api.types.is_integer_dtype(shipments[f"{side}_agent_id"]):
            table[f"{side}_agent_id"] = pd.array(table[f"{side}_agent_id"], dtype="Int64")
    original_geometry = dict(zip(shipments.transaction_id, shipments.geometry))
    for index, row in enumerate(output):
        if not row["routed"]:
            lines[index] = original_geometry[row["transaction_id"]]
    return geopandas.GeoDataFrame(table, geometry=lines, crs=shipments.crs)
