"""Load trips onto the road network, as MASS-GT's traffic assignment (TRAF)
does, generalized to any time intervals, speed classes and trip sources.

Every trip takes the cheapest path between the network nodes of its two
zones, all or nothing. A link's cost for a vehicle is its cost per hour
times the link's length over the speed of the vehicle's speed class, plus
its cost per kilometre times the length, unless a road-type cost fixes it,
as for connectors or links closed to some vehicles. Speeds are given per
link and speed class, and optionally per time interval; this stage does not
change them. A tour trip counts in the interval of its departure, a matrix
trip over the whole period. Loads are reported per link, interval, vehicle
and segment: the number of trips, their mean utilization and the speed.
"""

import multiprocessing
import warnings

import numpy as np
import pandas as pd
from scipy.sparse import coo_matrix, csr_matrix
from scipy.sparse.csgraph import dijkstra

from netsy.synth.agents import _zone_key

TRIP_COLUMNS = ("departure", "vehicle", "utilization", "origin_zone_id", "destination_zone_id")


def _intervals(table):
    starts = pd.to_numeric(table["start"], errors="coerce").to_numpy(float)
    ends = pd.to_numeric(table["end"], errors="coerce").to_numpy(float)
    if np.isnan(starts).any() or np.isnan(ends).any() or (ends <= starts).any():
        raise ValueError("time_intervals.csv: every interval needs a 'start' before its 'end'")
    order = np.argsort(starts)
    if (starts[order][1:] < ends[order][:-1]).any():
        raise ValueError("time_intervals.csv: intervals must not overlap")
    return table["time_interval"].astype(str).to_numpy()[order], starts[order], ends[order]


# Per worker: the graph of one routing class, the node of each zone, the link
# between each pair of nodes, and the trips by origin.
_STATE = {}


def _paths(origin, destinations):
    """The links of the cheapest path from `origin` to each node."""
    predecessors = dijkstra(_STATE["graph"], indices=origin, return_predecessors=True)[1]
    link_of = _STATE["link_of"]
    routes = {}
    for destination in destinations:
        if destination == origin:
            routes[destination] = np.empty(0, dtype=np.int64)
            continue
        nodes = [destination]
        while nodes[-1] != origin:
            previous = predecessors[nodes[-1]]
            if previous < 0:
                break
            nodes.append(previous)
        if nodes[-1] != origin:
            routes[destination] = None
            continue
        nodes.reverse()
        routes[destination] = np.array([link_of[(a, b)] for a, b in zip(nodes[:-1], nodes[1:])], dtype=np.int64)
    return routes


def _load(origins):
    """Sparse link x group matrices of trips and utilization sums for the
    trips from `origins`, and the trips that found no path.
    """
    links, groups = _STATE["link_count"], _STATE["group_count"]
    rows, columns, trips, utilization = [], [], [], []
    unrouted = 0.0
    for origin in origins:
        by_destination = _STATE["trips"][origin]
        routes = _paths(origin, list(by_destination))
        for destination, entries in by_destination.items():
            route = routes[destination]
            if route is None:
                unrouted += sum(count for _, count, _ in entries)
                continue
            if not len(route):
                continue
            for group, count, used in entries:
                rows.append(route)
                columns.append(np.full(len(route), group))
                trips.append(np.full(len(route), count))
                utilization.append(np.full(len(route), used))
    shape = (links, groups)
    if not rows:
        return csr_matrix(shape), csr_matrix(shape), unrouted
    rows, columns = np.concatenate(rows), np.concatenate(columns)
    return (
        coo_matrix((np.concatenate(trips), (rows, columns)), shape=shape).tocsr(),
        coo_matrix((np.concatenate(utilization), (rows, columns)), shape=shape).tocsr(),
        unrouted,
    )


def network_loads(network, zones, vehicles, speeds, road_costs, intervals, trip_tables, matrices, matrix_assignment, workers=1):
    """One row per link, time interval, vehicle and segment with any trips:
    `trips`, their mean `utilization`, and the link's `speed` for the
    vehicle. `trip_tables` are `{name: table}` of trips, each with a
    departure hour, vehicle, utilization and zones, and optionally a
    `segment` (otherwise the name); `matrices` is `(zone_ids, {name:
    matrix})` or None. Matrix trips have no time interval. Raises
    ValueError if the tables do not fit together, and warns of trips that
    find no path.
    """
    names, starts, ends = _intervals(intervals)
    period = ends[-1]

    for column in ("link_id", "from_node", "to_node", "length", "road_type"):
        if column not in network.columns:
            raise ValueError(f"network.gpkg: missing column {column!r}")
    if network["link_id"].duplicated().any():
        raise ValueError("network.gpkg: 'link_id' values must be unique")
    length = pd.to_numeric(network["length"], errors="coerce").to_numpy(float)
    if np.isnan(length).any() or (length < 0).any():
        raise ValueError("network.gpkg: 'length' must hold numbers of at least 0")
    node_ids = pd.Index(pd.unique(pd.concat([network["from_node"], network["to_node"]]).map(_zone_key)))
    tails = node_ids.get_indexer(network["from_node"].map(_zone_key))
    heads = node_ids.get_indexer(network["to_node"].map(_zone_key))
    link_ids = network["link_id"].map(_zone_key).to_numpy()
    road_types = network["road_type"].map(_zone_key).to_numpy()
    # Of parallel links, a path uses the first and the last sets the cost,
    # as in MASS-GT.
    link_of, last = {}, {}
    for index, pair in enumerate(zip(tails, heads)):
        link_of.setdefault(pair, index)
        last[pair] = index
    edges = np.array(list(last.values()))

    if "node" not in zones.columns:
        raise ValueError("zones.gpkg: missing 'node' column, the network node each zone loads at")
    zone_node = dict(zip(zones["zone_id"].map(_zone_key), node_ids.get_indexer(zones["node"].map(_zone_key))))
    if min(zone_node.values()) < 0:
        raise ValueError("zones.gpkg: every zone's 'node' must be a node of network.gpkg")

    vehicles = vehicles.set_index(vehicles["vehicle"].map(_zone_key))
    for column in ("speed_class", "cost_per_hour", "cost_per_km"):
        if column not in vehicles.columns:
            raise ValueError(f"assignment_vehicles.csv: missing column {column!r}")
    speed_keys = [column for column in ("time_interval",) if column in speeds.columns]
    speed_table = speeds.assign(
        link=pd.Index(link_ids).get_indexer(speeds["link_id"].map(_zone_key)),
        speed=pd.to_numeric(speeds["speed"], errors="coerce"),
        speed_class=speeds["speed_class"].map(_zone_key),
    )
    if (speed_table["link"] < 0).any():
        raise ValueError("link_speeds.csv: every 'link_id' must be a link of network.gpkg")
    if speed_table["speed"].isna().any() or (speed_table["speed"] <= 0).any():
        raise ValueError("link_speeds.csv: 'speed' must hold numbers above 0")

    def speed_of(speed_class, interval):
        rows = speed_table[speed_table["speed_class"] == speed_class]
        if speed_keys:
            rows = rows[rows["time_interval"].map(_zone_key) == interval]
        values = np.full(len(link_ids), np.nan)
        values[rows["link"].to_numpy()] = rows["speed"].to_numpy(float)
        if np.isnan(values).any():
            raise ValueError(f"link_speeds.csv: speed class {speed_class!r} needs a speed on every link"
                             + (f" in interval {interval!r}" if speed_keys else ""))
        return values

    fixed = {}
    for row in road_costs.to_dict("records"):
        speed_class = None if pd.isna(row.get("speed_class")) else _zone_key(row["speed_class"])
        fixed.setdefault(_zone_key(row["road_type"]), []).append((speed_class, float(row["cost"])))

    # Trips: (routing class, origin node) -> destination node -> entries of
    # (group, trips, utilization sum).
    groups, group_index = [], {}
    work = {}

    classes = {
        vehicle: (_zone_key(row["speed_class"]), float(row["cost_per_hour"]), float(row["cost_per_km"]))
        for vehicle, row in vehicles.iterrows()
    }

    def add(vehicle, interval, segment, origin, destination, count, used):
        if vehicle not in classes:
            raise ValueError(f"assignment_vehicles.csv: no row for vehicle {vehicle!r}")
        route_class = classes[vehicle] + (interval if speed_keys else None,)
        key = (interval, vehicle, segment)
        if key not in group_index:
            group_index[key] = len(groups)
            groups.append(key)
        trips_of = work.setdefault(route_class, {}).setdefault(zone_node[origin], {})
        trips_of.setdefault(zone_node[destination], []).append((group_index[key], count, used))

    for name, table in trip_tables.items():
        missing = [column for column in TRIP_COLUMNS if column not in table.columns]
        if missing:
            raise ValueError(f"{name}: missing columns {missing}")
        departure = pd.to_numeric(table["departure"], errors="coerce").to_numpy(float) % period
        which = np.searchsorted(ends, departure, side="right")
        inside = (which < len(ends)) & (departure >= starts[np.minimum(which, len(ends) - 1)])
        if not inside.all():
            raise ValueError(f"{name}: departures at {sorted(set(departure[~inside]))[:3]} fall in no time interval")
        segments = table["segment"].map(_zone_key) if "segment" in table.columns else pd.Series(name, index=table.index)
        used = pd.to_numeric(table["utilization"], errors="coerce").fillna(0).to_numpy(float)
        for origin, destination, vehicle, interval, segment, utilization in zip(
            table["origin_zone_id"].map(_zone_key), table["destination_zone_id"].map(_zone_key),
            table["vehicle"].map(_zone_key), names[which], segments, used,
        ):
            if origin not in zone_node or destination not in zone_node:
                raise ValueError(f"{name}: zones {origin!r} and {destination!r} must be in zones.gpkg")
            add(vehicle, interval, segment, origin, destination, 1.0, utilization)

    if matrices is not None:
        zone_ids, by_name = matrices
        for row in matrix_assignment.to_dict("records"):
            name = row["matrix"]
            if name not in by_name:
                raise ValueError(f"matrix_assignment.csv: no matrix {name!r} in trip_matrices.omx")
            matrix = by_name[name]
            minimum = float(row.get("minimum") or 0.0)
            utilization = float(row.get("utilization") or 0.0)
            origins, destinations = np.nonzero(matrix >= max(minimum, 1e-12))
            for o, d in zip(origins, destinations):
                if zone_ids[o] not in zone_node or zone_ids[d] not in zone_node:
                    continue
                count = float(matrix[o, d])
                add(_zone_key(row["vehicle"]), "", _zone_key(row["segment"]), zone_ids[o], zone_ids[d],
                    count, count * utilization)

    total_trips = csr_matrix((len(link_ids), max(len(groups), 1)))
    total_used = csr_matrix((len(link_ids), max(len(groups), 1)))
    unrouted = 0.0
    speed_by_class = {}
    for route_class, trips in work.items():
        speed_class, per_hour, per_km, interval = route_class
        speed = speed_of(speed_class, interval)
        speed_by_class[(speed_class, interval)] = speed
        cost = per_hour * length / speed + per_km * length
        for road_type, rules in fixed.items():
            for rule_class, value in rules:
                if rule_class in (None, speed_class):
                    cost[road_types == road_type] = value
        graph = csr_matrix((cost[edges], (tails[edges], heads[edges])), shape=(len(node_ids),) * 2)
        _STATE.update(graph=graph, link_of=link_of, trips=trips, link_count=len(link_ids), group_count=max(len(groups), 1))
        origins = list(trips)
        chunks = [origins[i::workers * 8] for i in range(workers * 8)] if workers > 1 else [origins]
        if workers > 1:
            with multiprocessing.get_context("fork").Pool(workers) as pool:
                results = pool.map(_load, chunks)
        else:
            results = [_load(chunk) for chunk in chunks]
        for loaded, used, missed in results:
            total_trips = total_trips + loaded
            total_used = total_used + used
            unrouted += missed
    _STATE.clear()

    total_trips = total_trips.tocoo()
    links, group_of, count = total_trips.row, total_trips.col, total_trips.data
    used = np.asarray(total_used.tocsr()[links, group_of]).ravel()
    keys = np.array(groups, dtype=object).reshape(-1, 3) if groups else np.empty((0, 3), dtype=object)
    speed = np.empty(len(links))
    for group, (interval, vehicle, _) in enumerate(groups):
        at = group_of == group
        speed[at] = speed_by_class[(classes[vehicle][0], interval if speed_keys else None)][links[at]]
    table = pd.DataFrame({
        "link_id": link_ids[links], "time_interval": keys[group_of, 0], "vehicle": keys[group_of, 1],
        "segment": keys[group_of, 2], "trips": count, "utilization": used / count, "speed": speed,
    })
    if unrouted:
        warnings.warn(f"{unrouted:g} trips found no path between their zones and were not loaded")
    return table.sort_values(["link_id", "time_interval", "vehicle", "segment"], kind="stable").reset_index(drop=True)
