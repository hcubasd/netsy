"""Form vehicle tours from shipments, as MASS-GT's tour formation (TOUR)
does, generalized to any carriers, strata and delivery windows.

Each shipment is first split into equal parts that fit its vehicle. A part
loaded or unloaded at a facility of a carrier type is carried by that
facility's carrier (one of the two, at random, when both ends are), and any
other part by one of a number of independent carriers, at random. Each
carrier then builds its tours one at a time from its parts, a based
carrier's shortest first and an independent carrier's in random order: a
tour starts with the first part left, and after each part a binary
logit decides whether it ends, its first decision with one set of
coefficients and the later ones with another. A tour that does not end takes
the remaining part closest to it that fits: of the same stratum, within the
capacity slack, and in a delivery window that goes with the tour's; a part
of the tour's vehicle counts as half as far. A tour also ends when it has
reached its maximum number of parts or duration, is full, has no part left
within the maximum proximity, or none fits. Its stops are sequenced
loading first, then unloading, nearest first, then improved by moving
single stops; it returns empty to its start. Its departure time centres its
stops' arrivals on their delivery windows.

A tour's attributes in the end-tour logits (its vehicle, the kinds of its
ends and its zones) are those of its first part, as in MASS-GT.
"""

import math

import geopandas
import numpy as np
import pandas as pd
from numba import njit
from shapely.geometry import LineString

from netsy.helpers.geometry import zone_points
from netsy.synth.agents import _zone_key
from netsy.synth.shipments import AGENT, ZONE, _intrazonal, _rows_for, _label

# Settings and their defaults (MASS-GT's): the number of independent
# carriers, a tour's largest number of parts after its first, its longest
# duration (h) and its farthest next part (km) for it to go on, the share of
# a vehicle's capacity a tour may fill when it takes a part, and the mean
# time (h) a vehicle spends at a stop, drawn uniformly between none and
# twice the mean, once per tour. `carrier_facility_type` and `same_stratum`
# may each be given more than once.
SETTINGS = {
    "independent_carriers": 100, "max_shipments": 10, "max_duration": 9.0, "max_proximity": 100.0,
    "capacity_slack": 1.1, "mean_dwell_time": 0.25,
}
LISTS = ("carrier_facility_type", "same_stratum")
TERMS = (
    "constant, duration, sqrt_duration, utilization, squared_utilization, proximity, log_stops, "
    "origin:<kind>, destination:<kind>, zone:<zone column>, vehicle:<vehicle>, resource:<resource>"
)


def _settings(table):
    values = dict(SETTINGS)
    lists = {name: [] for name in LISTS}
    for row in table.to_dict("records"):
        name, value = row["setting"], row["value"]
        if name in lists:
            lists[name].append(_zone_key(value))
        elif name in values:
            number = pd.to_numeric(value, errors="coerce")
            if pd.isna(number) or number < 0:
                raise ValueError(f"tour_settings.csv: {name!r} must be a number of at least 0")
            values[name] = float(number)
        else:
            raise ValueError(f"tour_settings.csv: unknown setting {name!r}; settings are {sorted(SETTINGS) + list(LISTS)}")
    values["independent_carriers"] = int(values["independent_carriers"])
    values["max_shipments"] = int(values["max_shipments"])
    if values["independent_carriers"] < 1:
        raise ValueError("tour_settings.csv: 'independent_carriers' must be at least 1")
    return values, lists


class _EndTour:
    """A binary end-tour logit: its terms for every stratum, and the
    probability that a tour ends.
    """

    def __init__(self, table, name, strata):
        self.table, self.name = table, name
        self.keys = [column for column in table.columns if column not in ("term", "value")]
        extra = sorted(set(self.keys) - set(strata))
        if extra:
            raise ValueError(f"{name}: columns {extra} are not shipment stratum columns")
        self.cache = {}

    def terms(self, stratum):
        key = tuple(stratum[column] for column in self.keys)
        if key not in self.cache:
            rows = _rows_for(self.table, self.keys, stratum)
            if rows.empty:
                raise ValueError(f"{self.name}: no coefficients for {_label(stratum, self.keys)}")
            terms = []
            for row in rows.to_dict("records"):
                term = row["term"]
                name, _, argument = term.partition(":")
                simple = ("constant", "duration", "sqrt_duration", "utilization", "squared_utilization", "proximity", "log_stops")
                if term not in simple and not (name in ("origin", "destination", "zone", "vehicle", "resource") and argument):
                    raise ValueError(f"{self.name}: unknown term {term!r}; terms are {TERMS}")
                terms.append((name, argument, row["value"]))
            self.cache[key] = terms
        return self.cache[key]

    def ends(self, stratum, features, rng):
        utility = 0.0
        for name, argument, value in self.terms(stratum):
            utility += value * features(name, argument)
        return rng.random() < 1 / (1 + math.exp(-utility))


def tours(zones, facilities, skims, shipments, vehicles, settings, end_tour_first, end_tour_later, rng):
    """One row per trip of every tour, and one row per shipment part with
    the tour that carries it: `(trips, parts)`. `facilities` may be None
    when no shipment uses one; `skims` is `(zone_ids, time, distance)`. `rng`
    is a numpy Generator, so a seeded one makes the result repeatable.
    Raises ValueError if the tables do not fit together.
    """
    values, lists = _settings(settings)
    zone_ids, time, distance = skims
    skim_index = {zone: index for index, zone in enumerate(zone_ids)}
    time, distance = _intrazonal(np.array(time, dtype=np.float32)), _intrazonal(np.array(distance, dtype=np.float32))
    zone_keys = zones["zone_id"].map(_zone_key)
    zone_original = dict(zip(zone_keys, zones["zone_id"]))
    skim_zone = {index: zone_original[zone] for zone, index in skim_index.items() if zone in zone_original}
    zone_point = {skim_index[key]: tuple(point) for key, point in zip(zone_keys, zone_points(zones)) if key in skim_index}

    required = ["transaction_id", "resource", "quantity", "vehicle", "origin_zone_id", "destination_zone_id"]
    missing = [column for column in required if column not in shipments.columns]
    if missing:
        raise ValueError(f"shipments.gpkg: missing columns {missing}")
    reserved = set(required) | {
        "origin_agent_id", "destination_agent_id", "flow_type", "origin_facility_id", "destination_facility_id",
        "size_class", "window", "window_start", "window_end", "geometry",
    }
    strata = ["resource"] + [column for column in shipments.columns if column not in reserved]
    for name in lists["same_stratum"]:
        if name not in strata:
            raise ValueError(f"tour_settings.csv: same_stratum {name!r} is not a stratum column of shipments.gpkg")

    def skim_of(column):
        keys = shipments[column].map(_zone_key)
        unknown = sorted(set(keys) - set(skim_index) | set(keys) - set(zone_original))
        if unknown:
            raise ValueError(f"shipments.gpkg: zones {unknown[:5]} are not in zones.gpkg and the skims")
        return keys.map(skim_index).to_numpy()

    origin, destination = skim_of("origin_zone_id"), skim_of("destination_zone_id")
    capacity_of = dict(zip(vehicles["vehicle"].map(_zone_key), vehicles["capacity"].astype(float)))
    vehicle = shipments["vehicle"].map(_zone_key).to_numpy()
    unknown = sorted(set(vehicle) - set(capacity_of))
    if unknown:
        raise ValueError(f"shipments.gpkg: vehicles {unknown} are not in shipment_vehicles.csv")
    quantity = pd.to_numeric(shipments["quantity"], errors="coerce").to_numpy(dtype=float)
    if np.isnan(quantity).any() or (quantity <= 0).any():
        raise ValueError("shipments.gpkg: 'quantity' must hold numbers above 0")

    # The kind of each end: an agent, a facility type, or a zone.
    facility_type, facility_zone = {}, {}
    if facilities is not None:
        facility_type = dict(zip(facilities["facility_id"].map(_zone_key), facilities["facility_type"].map(_zone_key)))
        facility_zone = dict(zip(facilities["facility_id"].map(_zone_key), facilities["zone_id"].map(_zone_key)))

    def kinds(side):
        agent = shipments.get(f"{side}_agent_id", pd.Series(np.nan, index=shipments.index))
        facility = shipments.get(f"{side}_facility_id", pd.Series(np.nan, index=shipments.index))
        result, ids = [], []
        for a, f in zip(agent, facility):
            if not pd.isna(f):
                key = _zone_key(f)
                if key not in facility_type:
                    raise ValueError(f"shipments.gpkg: facility {key!r} is not in facilities.gpkg")
                result.append(facility_type[key])
                ids.append(key)
            else:
                result.append(ZONE if pd.isna(a) else AGENT)
                ids.append(None)
        return np.array(result, dtype=object), ids

    origin_kind, origin_facility = kinds("origin")
    destination_kind, destination_facility = kinds("destination")

    # Delivery windows, in time order; a tour may mix two neighbouring ones,
    # the last and the first neighbouring across midnight.
    has_windows = "window_start" in shipments.columns
    if has_windows:
        bounds = list(zip(shipments["window_start"].astype(float), shipments["window_end"].astype(float)))
        ordered = sorted(set(bounds))
        window = np.array([ordered.index(bound) for bound in bounds])
        window_count = len(ordered)
    else:
        window = np.full(len(shipments), -1)
        window_count = 0
        bounds = [(math.nan, math.nan)] * len(shipments)
    stratum_rows = [dict(zip(strata, row)) for row in shipments[strata].map(_zone_key).itertuples(index=False, name=None)]
    same_key = pd.Series([tuple(row[name] for name in lists["same_stratum"]) for row in stratum_rows])
    same_code = pd.factorize(same_key)[0]

    # Parts: shipments split into equal parts that fit their vehicle.
    capacity = np.array([capacity_of[v] for v in vehicle])
    pieces = np.where(quantity > capacity, np.ceil(quantity / capacity), 1).astype(int)
    part_of = np.repeat(np.arange(len(shipments)), pieces)
    part_quantity = (quantity / pieces)[part_of]

    # Carriers: a facility of a carrier type at either end, or else one of
    # the independent carriers.
    bases = set(lists["carrier_facility_type"])
    carrier = np.empty(len(part_of), dtype=object)
    for index, ship in enumerate(part_of):
        ends = [f for f, kind in ((origin_facility[ship], origin_kind[ship]), (destination_facility[ship], destination_kind[ship])) if f and kind in bases]
        if ends:
            carrier[index] = ends[0] if len(ends) == 1 else ends[int(rng.integers(2))]
        else:
            carrier[index] = f"independent_{int(rng.integers(values['independent_carriers'])) + 1}"
    base_zone = {f: skim_index[facility_zone[f]] for f in set(carrier) if f in facility_zone}

    first_logit = _EndTour(end_tour_first, "end_tour_first.csv", strata)
    later_logit = _EndTour(end_tour_later, "end_tour_later.csv", strata)

    def duration(sequence):
        sequence = np.asarray(sequence)
        return float(time[sequence[:-1], sequence[1:]].sum())

    nearest_cache = {}

    def nearest(locations, remaining):
        """The smallest model proximity, once per state of a tour (the cache
        is cleared as each tour starts).
        """
        key = (len(locations), len(remaining))
        if key not in nearest_cache:
            nearest_cache.clear()
            nearest_cache[key] = float(proximity_model(locations, remaining).min())
        return nearest_cache[key]

    def proximity_model(locations, remaining):
        # The distance from the tour's nearest location to a part's loading
        # plus its unloading location, leaving out the tour's first loading
        # location unless its first part stays in its zone.
        first_load, first_unload = locations[0]
        stops = {zone for pair in locations for zone in pair}
        if first_load != first_unload:
            stops.discard(first_load)
        stops = np.fromiter(stops, dtype=int)
        loads, unloads = origin[part_of[remaining]], destination[part_of[remaining]]
        return (distance[np.ix_(stops, loads)] + distance[np.ix_(stops, unloads)]).min(axis=0)

    def proximity_select(locations, remaining):
        # The distance from the tour's nearest loading location to a part's
        # loading location plus from its nearest unloading location to the
        # part's unloading location.
        loading = np.unique([pair[0] for pair in locations])
        unloading = np.unique([pair[1] for pair in locations])
        loads, unloads = origin[part_of[remaining]], destination[part_of[remaining]]
        return distance[np.ix_(loading, loads)].min(axis=0) + distance[np.ix_(unloading, unloads)].min(axis=0)

    def select(tour, locations, remaining):
        first = part_of[tour[0]]
        ships = part_of[remaining]
        tour_capacity = capacity_of[vehicle[first]]
        fits = (part_quantity[tour].sum() + part_quantity[remaining]) / tour_capacity < values["capacity_slack"]
        fits &= same_code[ships] == same_code[first]
        if has_windows:
            windows = window[ships]
            if len(tour) == 1:
                own = window[first]
                near = np.abs(windows - own) <= 1
                if own == 0:
                    near |= windows == window_count - 1
                elif own == window_count - 1:
                    near |= windows == 0
            else:
                near = (windows == window[first]) | (windows == window[part_of[tour[1]]])
            fits &= near
        if not fits.any():
            return None
        proximity = proximity_select(locations, remaining)
        proximity = np.where(vehicle[ships] == vehicle[first], proximity / 2, proximity)
        candidates = np.flatnonzero(fits)
        return candidates[np.argmin(proximity[candidates])]

    def sequence(tour, locations, base):
        """MASS-GT's stop order: loading locations nearest first from the
        first, then the unloading locations of the earliest window and of
        the latest, nearest first; from the base, if any; with visits back
        to the start dropped; then single stops moved where that shortens
        the tour without unloading before loading.
        """
        windows = [window[part_of[part]] for part in tour]
        if has_windows and window_count > 1 and 0 in windows and window_count - 1 in windows:
            first_window, last_window = window_count - 1, 0
        else:
            first_window, last_window = min(windows), max(windows)
        loading = sorted({pair[0] for pair in locations})
        order = [locations[0][0]]
        loading.remove(order[0])
        while loading:
            nearest = min(loading, key=lambda zone: (time[order[-1], zone], loading.index(zone)))
            order.append(nearest)
            loading.remove(nearest)
        early = sorted({pair[1] for pair, w in zip(locations, windows) if w == first_window})
        late = sorted({pair[1] for pair, w in zip(locations, windows) if w == last_window and pair[1] not in early})
        for group in (early, late if first_window != last_window else []):
            group = list(group)
            while group:
                nearest = min(group, key=lambda zone: (time[order[-1], zone], group.index(zone)))
                order.append(nearest)
                group.remove(nearest)
        if base is not None and order[0] != base:
            order = [base] + order
        back = [index for index in range(1, len(order)) if order[index] == order[0]]
        if len(back) > 1:
            order = [zone for index, zone in enumerate(order) if index not in back] + [order[0]]
        if len(order) > 3:
            local = np.array(sorted(set(order)))
            at = {zone: index for index, zone in enumerate(local)}
            travel = time[np.ix_(local, local)].astype(np.float64)
            moved = _relocate(
                np.array([at[zone] for zone in order]), travel,
                np.array([at[load] for load, _ in locations]), np.array([at[unload] for _, unload in locations]),
            )
            order = [int(local[index]) for index in moved]
        return order

    zone_columns = {}

    def zone_column(column):
        if column not in zone_columns:
            if column not in zones.columns:
                raise ValueError(f"end-tour terms: zones.gpkg has no column {column!r}")
            numbers = pd.to_numeric(zones[column], errors="coerce")
            if numbers.isna().any():
                raise ValueError(f"zones.gpkg: '{column}' must hold numbers in every row")
            by_skim = np.zeros(len(zone_ids))
            by_skim[zone_keys.map(skim_index).to_numpy()] = numbers.to_numpy(dtype=float)
            zone_columns[column] = by_skim
        return zone_columns[column]

    trips, assignments = [], []
    tour_number = 0
    by_carrier = pd.Series(np.arange(len(part_of))).groupby(carrier, sort=True).indices
    for name in sorted(by_carrier):
        remaining = np.array(rng.permutation(by_carrier[name]))
        base = base_zone.get(name)
        if base is not None:
            # A based carrier takes its parts shortest first, as MASS-GT
            # meant to (its code sorts by the loading zone's intrazonal
            # distance instead, which gives the same tours).
            remaining = remaining[np.argsort(distance[origin[part_of[remaining]], destination[part_of[remaining]]], kind="stable")]
        while len(remaining):
            first, remaining = remaining[0], remaining[1:]
            nearest_cache.clear()
            ship = part_of[first]
            tour = [first]
            locations = [(int(origin[ship]), int(destination[ship]))]
            order = [locations[0][0], locations[0][1]]
            stratum = stratum_rows[ship]
            tour_capacity = capacity_of[vehicle[ship]]

            def features(term, argument, tour=tour, locations=locations):
                if term == "constant":
                    return 1.0
                if term in ("duration", "sqrt_duration"):
                    hours = duration(order)
                    return math.sqrt(hours) if term == "sqrt_duration" else hours
                if term in ("utilization", "squared_utilization"):
                    used = part_quantity[tour].sum() / tour_capacity
                    return used ** 2 if term == "squared_utilization" else used
                if term == "proximity":
                    return nearest(locations, remaining)
                if term == "log_stops":
                    return math.log(len({zone for pair in locations for zone in pair}))
                if term == "origin":
                    return float(origin_kind[ship] == argument)
                if term == "destination":
                    return float(destination_kind[ship] == argument)
                if term == "zone":
                    column = zone_column(argument)
                    return float(max(column[origin[ship]], column[destination[ship]]))
                if term == "vehicle":
                    return float(vehicle[ship] == argument)
                weights = {}
                for part in tour:
                    key = stratum_rows[part_of[part]]["resource"]
                    weights[key] = weights.get(key, 0.0) + part_quantity[part]
                return float(max(sorted(weights), key=lambda key: weights[key]) == argument)

            def may_go_on():
                return (
                    len(tour) - 1 < values["max_shipments"] and duration(order) < values["max_duration"]
                    and part_quantity[tour].sum() / tour_capacity < 1
                    and nearest(locations, remaining) < values["max_proximity"]
                )

            if len(remaining) and may_go_on() and not first_logit.ends(stratum, features, rng):
                while len(remaining) and may_go_on():
                    chosen = select(tour, locations, remaining)
                    if chosen is None:
                        break
                    part, remaining = remaining[int(chosen)], np.delete(remaining, int(chosen))
                    tour.append(part)
                    locations.append((int(origin[part_of[part]]), int(destination[part_of[part]])))
                    order[:] = sequence(tour, locations, base)
                    if not len(remaining) or later_logit.ends(stratum, features, rng):
                        break
            tour_number += 1
            trips.extend(_trips(
                tour_number, name, tour, order, part_of, part_quantity, origin, destination, window, bounds,
                window_count, has_windows, time, values["mean_dwell_time"], rng,
            ))
            assignments.extend((part_of[part], tour_number, part_quantity[part]) for part in tour)

    return _tables(
        trips, assignments, shipments, strata, stratum_rows, vehicle, part_quantity, part_of, skim_zone, zone_point,
        capacity_of, zones.crs,
    )


@njit(cache=True)
def _relocate(order, travel, loads, unloads):
    """MASS-GT's improvement of a stop order: for every pair of positions in
    turn, the stop at the second moves to the first where that shortens the
    tour and no location is unloaded before it is loaded. Each move is
    judged by the change in duration around it.
    """
    count = len(order)
    order = order.copy()
    rest = np.empty(count - 1, np.int64)
    moved = np.empty(count, np.int64)
    for a in range(1, count):
        for b in range(1, count):
            if a == b:
                continue
            stop = order[b]
            change = -travel[order[b - 1], stop]
            if b + 1 < count:
                change += travel[order[b - 1], order[b + 1]] - travel[stop, order[b + 1]]
            k = 0
            for i in range(count):
                if i != b:
                    rest[k] = order[i]
                    k += 1
            if a < count - 1:
                change += travel[rest[a - 1], stop] + travel[stop, rest[a]] - travel[rest[a - 1], rest[a]]
            else:
                change += travel[rest[count - 2], stop]
            if change >= -1e-12:
                continue
            k = 0
            for i in range(count):
                if i == a:
                    moved[i] = stop
                else:
                    moved[i] = rest[k]
                    k += 1
            feasible = True
            for p in range(len(loads)):
                first_load = -1
                for i in range(count):
                    if moved[i] == loads[p]:
                        first_load = i
                        break
                last_unload = -1
                for i in range(count - 1, -1, -1):
                    if moved[i] == unloads[p]:
                        last_unload = i
                        break
                if last_unload <= first_load:
                    feasible = False
                    break
            if feasible:
                order[:] = moved
    return order


def _trips(tour_id, carrier, tour, order, part_of, part_quantity, origin, destination, window, bounds,
           window_count, has_windows, time, mean_dwell, rng):
    """The trips of one tour: its stops in order, returning to its start,
    with the load on board and the departure and arrival times.
    """
    stops = list(order)
    empty_return = stops[0] != stops[-1]
    if empty_return:
        stops.append(stops[0])
    windows = {window[part_of[part]] for part in tour}
    past_midnight = has_windows and window_count > 1 and 0 in windows and window_count - 1 in windows
    loaded, unloaded = set(), set()
    load, rows = 0.0, []
    for trip in range(len(stops) - 1):
        here = stops[trip]
        lower = upper = None
        for part in tour:
            ship = part_of[part]
            if origin[ship] == here and part not in loaded and part not in unloaded:
                load += part_quantity[part]
                loaded.add(part)
            if destination[ship] == here and part in loaded and part not in unloaded:
                load -= part_quantity[part]
                unloaded.add(part)
                if has_windows:
                    start, end = bounds[ship]
                    if window[ship] == 0 and past_midnight:
                        start, end = start + 24, end + 24
                    lower = start if lower is None else min(lower, start)
                    upper = end if upper is None else max(upper, end)
        rows.append({"from": here, "to": stops[trip + 1], "load": max(load, 0.0), "lower": lower, "upper": upper})
    # MASS-GT's departure time: with one dwell time for every stop, the
    # departure that puts the trips' arrivals, on average, midway between
    # their earliest and latest window bounds.
    dwell = mean_dwell * 2 * rng.random()
    clock, early, late = 0.0, [], []
    for row in rows:
        row["departure"] = clock
        row["arrival"] = clock + float(time[row["from"], row["to"]])
        clock = row["arrival"] + dwell
        if row["lower"] is not None:
            early.append(row["lower"] - row["arrival"])
            late.append(row["upper"] - row["arrival"])
    start = (np.mean(early) + np.mean(late)) / 2 if early else 0.0
    if start < 0:
        start += 24
    for row in rows:
        row["departure"] += start
        row["arrival"] += start
    total = float(part_quantity[tour].sum())
    return [
        {**row, "tour_id": tour_id, "trip": number + 1, "carrier": carrier, "tour": tour, "start": start,
         "total": total, "empty": empty_return and number == len(rows) - 1}
        for number, row in enumerate(rows)
    ]


def _tables(trips, assignments, shipments, strata, stratum_rows, vehicle, part_quantity, part_of, skim_zone, zone_point,
            capacity_of, crs):
    rows = []
    for trip in trips:
        tour = trip["tour"]
        first = part_of[tour[0]]
        weights = {}
        for part in tour:
            key = stratum_rows[part_of[part]]["resource"]
            weights[key] = weights.get(key, 0.0) + part_quantity[part]
        resource = max(sorted(weights), key=lambda key: weights[key])
        row = {
            "tour_id": trip["tour_id"], "trip": trip["trip"], "carrier": trip["carrier"], "vehicle": vehicle[first],
            "resource": None if trip["empty"] else resource,
        }
        row.update({column: stratum_rows[first][column] for column in strata if column != "resource"})
        row.update({
            "shipments": len(tour), "tour_quantity": trip["total"], "quantity": trip["load"],
            "utilization": trip["load"] / capacity_of[vehicle[first]],
            "tour_departure": trip["start"], "departure": trip["departure"], "arrival": trip["arrival"],
            "origin_zone_id": skim_zone[trip["from"]], "destination_zone_id": skim_zone[trip["to"]],
        })
        rows.append(row)
    lines = [LineString([zone_point[trip["from"]], zone_point[trip["to"]]]) for trip in trips]
    table = geopandas.GeoDataFrame(rows, geometry=lines, crs=crs)
    ids = shipments["transaction_id"].to_numpy()
    parts = pd.DataFrame(
        [(ids[ship], tour_id, quantity) for ship, tour_id, quantity in assignments],
        columns=["transaction_id", "tour_id", "quantity"],
    ).sort_values(["transaction_id", "tour_id"], kind="stable").reset_index(drop=True)
    return table, parts
