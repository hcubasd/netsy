"""Delivery tours from depots, as MASS-GT's parcel scheduling module
(PARCEL_SCHD) forms them, with a better routing method as an option.

With MASS-GT's routing, a depot first sends full vehicles to any zone with at
least a vehicle load of its parcels. It then sorts its other parcels by
distance, farthest first, and gives each new tour the farthest parcel left
and the parcels nearest it, up to the vehicle load; the parcels left over
form one more tour. Distance here is the sum of the road distance and the
straight-line distance between zones, each as a share of its total over
all pairs. A tour visits its zones nearest first from the depot, then swaps
pairs of stops where that shortens it, and returns to the depot.

With savings routing (a contribution to the port), each depot's tours are
built by the Clarke-Wright savings algorithm instead, under the same
vehicle load, and every tour is then improved by moving single stops; the
same parcels reach the same zones, by fewer vehicle-kilometres.

Either way, a tour departs at an hour drawn from the departure
distribution, spends the drop time per parcel at each stop, and every trip
carries the parcels still on board.
"""

import geopandas
import numpy as np
import pandas as pd
from shapely.geometry import LineString

from netsy.helpers.geometry import zone_points
from netsy.synth.agents import _zone_key
from netsy.synth.shipments import _intrazonal

SETTINGS = {"max_load": 180.0, "drop_time": 0.0, "vehicle": "van", "segment": "parcel_deliveries", "utilization": 0.5}
ROUTINGS = ("massgt", "savings")


def _settings(table):
    values = dict(SETTINGS)
    for row in table.to_dict("records"):
        name = row["setting"]
        if name not in values:
            raise ValueError(f"delivery_settings.csv: unknown setting {name!r}; settings are {sorted(SETTINGS)}")
        values[name] = row["value"]
    for name in ("max_load", "drop_time", "utilization"):
        number = pd.to_numeric(values[name], errors="coerce")
        if pd.isna(number) or number < 0 or (name == "max_load" and number < 1):
            raise ValueError(f"delivery_settings.csv: {name!r} must be a number of at least {1 if name == 'max_load' else 0}")
        values[name] = float(number)
    values["max_load"] = int(values["max_load"])
    return values


def _clusters_massgt(origin, destinations, max_load, closeness):
    """MASS-GT's parcel clusters for one depot: a cluster id per parcel."""
    clusters = np.full(len(destinations), -1)
    next_id = 0
    # Full vehicles to any zone with a vehicle load of parcels.
    for zone in np.unique(destinations):
        indices = np.flatnonzero(destinations == zone)
        for _ in range(len(indices) // max_load):
            clusters[indices[:max_load]] = next_id
            indices = indices[max_load:]
            next_id += 1
    left = np.flatnonzero(clusters == -1)
    if not len(left):
        return clusters
    left = left[np.argsort(-closeness[origin, destinations[left]], kind="stable")]
    tours = int(np.ceil(len(left) / max_load))
    if tours == 1:
        clusters[left] = next_id
        return clusters
    dests = destinations[left]
    assigned = np.full(len(left), -1)
    for _ in range(tours):
        first = np.flatnonzero(assigned == -1)[0]
        assigned[first] = next_id
        distances = closeness[dests[first], dests].astype(float)
        distances[first] = 99999
        distances[assigned != -1] = 99999
        # As in MASS-GT, the nearest vehicle load less one, which may take
        # parcels of earlier clusters once none are left.
        assigned[np.argsort(distances)[:max_load - 1]] = next_id
        next_id += 1
    assigned[assigned == -1] = next_id
    clusters[left] = assigned
    return clusters


def _route_massgt(depot, stops, distance):
    """MASS-GT's stop order: nearest first, then pairwise swaps."""
    tour, left = [depot], list(stops)
    while left:
        nearest = int(np.argmin([distance[tour[-1], zone] for zone in left]))
        tour.append(left.pop(nearest))
    tour.append(depot)
    tour = np.array(tour)
    length = distance[tour[:-1], tour[1:]].sum()
    if len(tour) > 4:
        for a in range(1, len(tour) - 1):
            for b in range(1, len(tour) - 1):
                if a == b:
                    continue
                swapped = tour.copy()
                swapped[a], swapped[b] = tour[b], tour[a]
                swapped_length = distance[swapped[:-1], swapped[1:]].sum()
                if swapped_length < length:
                    tour, length = swapped, swapped_length
    return list(tour)


def _improve(route, distance):
    """`route` (depot first and last) with single stops moved while that
    shortens it, each time the move that shortens it most.
    """
    # Work on the route's own distances in double precision: in the skims'
    # single precision a move can seem to gain by rounding alone, and loop.
    zones = np.unique(route)
    distance = distance[np.ix_(zones, zones)].astype(np.float64)
    nodes = np.searchsorted(zones, route)
    while len(nodes) > 3:
        before, stops, after = nodes[:-2], nodes[1:-1], nodes[2:]
        # What taking each stop out saves, and what putting it between each
        # pair of consecutive locations costs.
        saved = distance[before, stops] + distance[stops, after] - distance[before, after]
        tails, heads = nodes[:-1], nodes[1:]
        cost = distance[np.ix_(tails, stops)] + distance[np.ix_(stops, heads)].T - distance[tails, heads][:, None]
        # Not into the pairs on either side of the stop, where it already is.
        positions = np.arange(len(stops))
        cost[positions, positions] = np.inf
        cost[positions + 1, positions] = np.inf
        delta = cost - saved[None, :]
        pair, stop = np.unravel_index(np.argmin(delta), delta.shape)
        if delta[pair, stop] >= -1e-9:
            break
        moved = np.delete(nodes, stop + 1)
        # Pair (pair, pair + 1) of the old order starts one place earlier
        # once the stop before it has gone.
        nodes = np.insert(moved, pair + 1 if pair < stop + 1 else pair, nodes[stop + 1])
    return [int(zones[node]) for node in nodes]


def _routes_savings(depot, stops, loads, max_load, distance):
    """Clarke-Wright savings routes for one depot's stops, each with a load
    of at most `max_load`, then improved by moving single stops.
    """
    count = len(stops)
    routes = {index: [index] for index in range(count)}
    route_of = list(range(count))
    load = {index: loads[index] for index in range(count)}
    stops = np.asarray(stops)
    to_depot, from_depot = distance[stops, depot], distance[depot, stops]
    savings = to_depot[:, None] + from_depot[None, :] - distance[np.ix_(stops, stops)]
    np.fill_diagonal(savings, -np.inf)
    order = np.argsort(-savings, axis=None, kind="stable")
    for flat in order:
        i, j = divmod(int(flat), count)
        if savings[i, j] <= 0:
            break
        a, b = route_of[i], route_of[j]
        # Join a route that ends at i to one that starts at j.
        if a == b or routes[a][-1] != i or routes[b][0] != j or load[a] + load[b] > max_load:
            continue
        routes[a] += routes.pop(b)
        load[a] += load.pop(b)
        for stop in routes[a]:
            route_of[stop] = a
    return [_improve([depot] + [int(stops[s]) for s in route] + [depot], distance) for route in routes.values()]


def deliveries(zones, skims, demand, settings, departures, rng, routing="massgt", vehicles=None):
    """One row per trip of every delivery tour: `tour_id`, `trip`,
    `carrier` (the depot), `operator`, `vehicle`, `segment`, `parcels`
    delivered at its destination, `quantity` on board, `utilization`,
    `tour_departure`, `departure` and `arrival` (hours), its zones, and a
    line between them. `skims` is `(zone_ids, time, distance)`. Raises
    ValueError if the tables do not fit together.
    """
    if routing not in ROUTINGS:
        raise ValueError(f"routing must be one of {ROUTINGS}")
    values = _settings(settings)
    zone_ids, time, distance = skims
    skim_index = {zone: index for index, zone in enumerate(zone_ids)}
    time, distance = _intrazonal(np.array(time, dtype=np.float32)), _intrazonal(np.array(distance, dtype=np.float32))
    keys = zones["zone_id"].map(_zone_key)
    missing = sorted(set(skim_index) - set(keys))
    if missing and routing == "massgt":
        raise ValueError(f"zones.gpkg: MASS-GT's routing needs a point for every zone of the skims; {missing[:5]} have none")
    point_of = dict(zip(keys.map(skim_index), map(tuple, zone_points(zones))))
    original = dict(zip(keys.map(skim_index), zones["zone_id"]))

    cdf = pd.to_numeric(departures["cumulative_share"], errors="coerce").to_numpy(dtype=float)
    hours = pd.to_numeric(departures["hour"], errors="coerce").to_numpy(dtype=float)
    if np.isnan(cdf).any() or np.isnan(hours).any() or (np.diff(cdf) < 0).any() or cdf[-1] < 1 - 1e-9:
        raise ValueError("delivery_departures.csv: 'cumulative_share' must rise to one by 'hour'")

    if routing == "massgt":
        # Road and straight-line distance, each as a share of its total.
        xy = np.array([point_of[index] for index in range(len(zone_ids))])
        straight = np.sqrt(((xy[:, None, :] - xy[None, :, :]) ** 2).sum(axis=2))
        closeness = distance / distance.sum(dtype=np.float64) + straight / straight.sum()
        del straight

    for column in ("destination_zone_id", "origin_zone_id", "facility_id", "operator", "parcels"):
        if column not in demand.columns:
            raise ValueError(f"parcel_demand.csv: missing column {column!r}")
    demand = demand.assign(
        destination=demand["destination_zone_id"].map(_zone_key).map(skim_index),
        origin=demand["origin_zone_id"].map(_zone_key).map(skim_index),
        parcels=pd.to_numeric(demand["parcels"], errors="coerce"),
    )
    if demand[["destination", "origin"]].isna().any().any():
        raise ValueError("parcel_demand.csv: zones must be in the skims")

    rows, tour_number = [], 0
    max_load = values["max_load"]
    if "delivery_group" in demand:
        demand["delivery_group"] = demand.delivery_group.fillna(demand.facility_id)
    group_columns = ["facility_id"] + [c for c in ("operator", "vehicle", "leg", "delivery_group") if c in demand]
    per_vehicle = {} if vehicles is None else vehicles.set_index("vehicle").to_dict("index")
    for _, group in demand.groupby(group_columns, sort=True):
        depot_id = _zone_key(group["facility_id"].iloc[0])
        active = dict(values)
        if "vehicle" in group:
            active["vehicle"] = group.vehicle.iloc[0]
            if active["vehicle"] not in per_vehicle:
                raise ValueError(f"delivery_vehicles.csv: no parameters for {active['vehicle']!r}")
            for c, value in per_vehicle[active["vehicle"]].items():
                if not pd.isna(value): active[c] = float(value)
        max_load = int(active["max_load"])
        if max_load != float(active["max_load"]) or not 0 <= float(active["utilization"]) <= 1 or float(active["drop_time"]) < 0 or float(active.get("speed_multiplier", 1)) <= 0 or float(active.get("speed_kmh", 1)) <= 0:
            raise ValueError("delivery vehicle parameters: whole capacity, nonnegative drop time, positive speed, and utilization in [0,1] required")
        if max_load < 1: raise ValueError("delivery vehicle capacity must be positive")
        depot = int(group["origin"].iloc[0])
        operator = group["operator"].iloc[0]
        stops = group.groupby("destination")["parcels"].sum()
        if routing == "massgt":
            destinations = np.repeat(stops.index.to_numpy(dtype=int), stops.to_numpy(dtype=int))
            clusters = _clusters_massgt(depot, destinations, max_load, closeness)
            tours = []
            for cluster in np.unique(clusters):
                counts = pd.Series(destinations[clusters == cluster]).value_counts().sort_index()
                tours.append((_route_massgt(depot, counts.index.tolist(), distance), counts.to_dict()))
        else:
            full, rest = {}, {}
            tours = []
            for zone, parcels in stops.items():
                for _ in range(int(parcels) // max_load):
                    tours.append(([depot, int(zone), depot], {int(zone): max_load}))
                if int(parcels) % max_load:
                    rest[int(zone)] = int(parcels) % max_load
            if rest:
                zones_left = list(rest)
                for route in _routes_savings(depot, zones_left, [rest[z] for z in zones_left], max_load, distance):
                    tours.append((route, {zone: rest[zone] for zone in route[1:-1]}))
        for route, delivered in tours:
            tour_number += 1
            hour = hours[np.searchsorted(cdf, rng.random(), side="right")] - 1 + rng.random()
            on_board = float(sum(delivered.values()))
            clock = hour
            for trip, (a, b) in enumerate(zip(route[:-1], route[1:])):
                parcels = delivered.get(b, 0) if trip < len(route) - 2 else 0
                travel = float(distance[a, b]) / float(active["speed_kmh"]) if "speed_kmh" in active else float(time[a, b]) / float(active.get("speed_multiplier", 1))
                rows.append({
                    "tour_id": tour_number, "trip": trip + 1, "carrier": depot_id, "operator": operator,
                    "vehicle": active["vehicle"], "segment": values["segment"], "parcels": parcels,
                    "quantity": on_board, "utilization": active["utilization"], "tour_departure": hour,
                    "departure": clock, "arrival": clock + travel, "from": a, "to": b,
                })
                on_board -= parcels
                if "leg" in group:
                    rows[-1].update(leg=group.leg.iloc[0], final_delivery=str(group.final_delivery.iloc[0]).lower() == 'true')
                clock += travel + active["drop_time"] * parcels
    table = pd.DataFrame(rows)
    lines = [LineString([point_of[a], point_of[b]]) for a, b in zip(table["from"], table["to"])]
    table["origin_zone_id"] = table.pop("from").map(original)
    table["destination_zone_id"] = table.pop("to").map(original)
    return geopandas.GeoDataFrame(table, geometry=lines, crs=zones.crs)
