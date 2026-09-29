import math
import warnings
from collections import defaultdict

import numpy as np
from scipy.sparse import lil_matrix
from scipy.sparse.csgraph import dijkstra
from scipy.spatial import KDTree


_COORD_PRECISION = 10


def _draw(items, weights, rng):
    weights = np.asarray(weights, dtype=float)
    return items[int(rng.choice(len(items), p=weights / weights.sum()))]


def _mnl_choice(items, utilities, rng):
    utilities = np.asarray(utilities, dtype=float)
    weights = np.exp(utilities - utilities.max())
    return _draw(items, weights, rng)


def _velocity(free_flow, grade, forward, alpha, beta, v_over_c):
    signed_grade = grade if forward else -grade
    effective = max(free_flow * math.exp(-signed_grade / 100), 1e-9)
    return effective / (1 + alpha * v_over_c ** beta)


def _index_nodes(links):
    index, coordinates = {}, []
    for link in links:
        for field, endpoint in (("a", "start"), ("b", "end")):
            coordinate = tuple(round(value, _COORD_PRECISION) for value in link[endpoint])
            if coordinate not in index:
                index[coordinate] = len(coordinates)
                coordinates.append(coordinate)
            link[field] = index[coordinate]
    return coordinates


def _graph(links, vehicle, vehicle_speeds, vehicle_params, v_over_c):
    """Return a directed generalized-cost graph and its link traversals."""
    n_nodes = max(max(link["a"], link["b"]) for link in links) + 1
    graph = lil_matrix((n_nodes, n_nodes))
    arcs = {}
    for link in links:
        free_flow = vehicle_speeds.get(link["road_type"])
        if free_flow is None:
            continue
        for source, target, forward in ((link["a"], link["b"], True), (link["b"], link["a"], False)):
            if not forward and link["oneway"]:
                continue
            velocity = _velocity(
                free_flow, link["grade"], forward, vehicle_params["bpr_alpha"],
                vehicle_params["bpr_beta"], v_over_c.get(link["link_id"], 0),
            )
            travel_time = link["length"] / velocity
            cost = max(
                -vehicle_params["time_coefficient"] * travel_time
                - vehicle_params["distance_coefficient"] * link["length"],
                1e-12,
            )
            previous = graph[source, target]
            if previous == 0 or cost < previous:
                graph[source, target] = cost
                arcs[(source, target)] = (link["link_id"], forward)
    return graph.tocsr(), arcs


def _route(predecessors, source, target, arcs):
    if source == target:
        return []
    path, node = [], target
    while node != source:
        previous = predecessors[node]
        if previous < 0 or (previous, node) not in arcs:
            return None
        path.append(arcs[(previous, node)])
        node = previous
    return list(reversed(path))


def _targets(desire_lines, departures, intervals):
    """Apportion each resource's integer total across valid intervals exactly."""
    totals = defaultdict(int)
    for line in desire_lines:
        totals[line["resource"]] += int(line["quantity"])
    positions = {interval: position for position, interval in enumerate(intervals)}
    probabilities = defaultdict(dict)
    for row in departures:
        if row["time_interval"] in positions:
            probabilities[row["resource"]][row["time_interval"]] = float(row["probability"])

    targets = {}
    for resource, total in totals.items():
        shares = probabilities[resource]
        normalizer = sum(shares.values())
        if normalizer <= 0:
            continue
        raw = {interval: total * probability / normalizer for interval, probability in shares.items()}
        apportioned = {interval: math.floor(value) for interval, value in raw.items()}
        remainder = total - sum(apportioned.values())
        order = sorted(shares, key=lambda interval: (-(raw[interval] - apportioned[interval]), positions[interval]))
        for interval in order[:remainder]:
            apportioned[interval] += 1
        targets.update({(resource, interval): amount for interval, amount in apportioned.items()})
    return targets


def _shipments(desire_lines):
    shipments = {}
    for line in desire_lines:
        start, end = list(line["geometry"].coords)
        key = (line["resource"], line["origin_agent_id"])
        shipment = shipments.setdefault(key, {
            "resource": line["resource"],
            "origin": start,
            "destinations": [],
        })
        shipment["destinations"].append({"point": end, "remaining": int(line["quantity"])})
    return list(shipments.values())


def _metrics(route, links_by_id, vehicle, speeds, params, v_over_c):
    travel_time = distance = 0.0
    for link_id, forward in route:
        link = links_by_id[link_id]
        velocity = _velocity(
            speeds[link["road_type"]], link["grade"], forward, params["bpr_alpha"],
            params["bpr_beta"], v_over_c.get(link_id, 0),
        )
        travel_time += link["length"] / velocity
        distance += link["length"]
    return travel_time, distance


def _path_cache(graphs, links_by_id, vehicles, speeds, v_over_c):
    cache = {}

    def path(vehicle, source, target):
        key = (vehicle, source, target)
        if key in cache:
            return cache[key]
        graph, arcs = graphs[vehicle]
        if source == target:
            cache[key] = ([], 0.0, 0.0)
            return cache[key]
        _, predecessors = dijkstra(graph, directed=True, indices=source, return_predecessors=True)
        route = _route(predecessors, source, target, arcs)
        if route is None:
            cache[key] = None
            return None
        time, distance = _metrics(route, links_by_id, vehicle, speeds[vehicle], vehicles[vehicle], v_over_c)
        cache[key] = (route, time, distance)
        return cache[key]

    return path


def _candidate_tour(shipment, seed_index, source, nodes, vehicle, resource, budget, capacity, path):
    """Construct one vehicle's closed, capacity-constrained cheapest-insertion tour."""
    room = min(capacity, budget)
    seed = shipment["destinations"][seed_index]
    seed_amount = min(seed["remaining"], room)
    if seed_amount <= 0:
        return None
    stops = [{"index": seed_index, "node": nodes[seed_index], "quantity": seed_amount}]
    room -= seed_amount

    def route_metrics(candidate_stops):
        sequence = [source] + [stop["node"] for stop in candidate_stops] + [source]
        legs = [path(vehicle["name"], start, end) for start, end in zip(sequence, sequence[1:])]
        if any(leg is None for leg in legs):
            return None
        return sum(leg[1] for leg in legs), sum(leg[2] for leg in legs), legs

    metrics = route_metrics(stops)
    if metrics is None:
        return None

    while room > 0:
        # Serve more of an existing stop before adding another stop.
        extended = False
        for stop in stops:
            destination = shipment["destinations"][stop["index"]]
            amount = min(destination["remaining"] - stop["quantity"], room)
            if amount > 0:
                stop["quantity"] += amount
                room -= amount
                extended = True
                break
        if extended:
            continue

        best = None
        for index, destination in enumerate(shipment["destinations"]):
            if destination["remaining"] <= 0 or any(stop["index"] == index for stop in stops):
                continue
            amount = min(destination["remaining"], room)
            for position in range(len(stops) + 1):
                proposal = stops[:position] + [{"index": index, "node": nodes[index], "quantity": amount}] + stops[position:]
                proposal_metrics = route_metrics(proposal)
                if proposal_metrics is None:
                    continue
                if best is None:
                    best = (proposal, proposal_metrics)
                    continue
                old_time, old_distance, _ = best[1]
                new_time, new_distance, _ = proposal_metrics
                old_cost = -vehicle["time_coefficient"] * old_time - vehicle["distance_coefficient"] * old_distance
                new_cost = -vehicle["time_coefficient"] * new_time - vehicle["distance_coefficient"] * new_distance
                if new_cost < old_cost:
                    best = (proposal, proposal_metrics)
        if best is None:
            break
        stops, metrics = best
        room = min(capacity, budget) - sum(stop["quantity"] for stop in stops)

    travel_time, distance, legs = metrics
    return {"vehicle": vehicle, "stops": stops, "legs": legs, "time": travel_time, "distance": distance}


def _trip(candidate, resource, dwell_time):
    payload = sum(stop["quantity"] for stop in candidate["stops"])
    segments = []
    for stop, leg in zip(candidate["stops"], candidate["legs"][:-1]):
        segments.append({"kind": "move", "route": leg[0], "payload": payload})
        segments.append({"kind": "dwell", "remaining": dwell_time})
        payload -= stop["quantity"]
    segments.append({"kind": "move", "route": candidate["legs"][-1][0], "payload": 0})
    return {
        "vehicle": candidate["vehicle"]["name"],
        "resource": resource,
        "segments": segments,
        "segment": 0,
        "link": 0,
        "progress": 0.0,
    }


def _advance(trip, duration, links_by_id, speeds, vehicles, v_over_c):
    """Advance a route through movement and dwell segments for one interval."""
    touched = []
    remaining = duration
    while remaining > 0 and trip["segment"] < len(trip["segments"]):
        segment = trip["segments"][trip["segment"]]
        if segment["kind"] == "dwell":
            elapsed = min(remaining, segment["remaining"])
            remaining -= elapsed
            segment["remaining"] -= elapsed
            if segment["remaining"] == 0:
                trip["segment"] += 1
            continue

        if trip["link"] >= len(segment["route"]):
            trip["segment"] += 1
            trip["link"] = 0
            trip["progress"] = 0.0
            continue
        link_id, forward = segment["route"][trip["link"]]
        link = links_by_id[link_id]
        velocity = _velocity(
            speeds[trip["vehicle"]][link["road_type"]], link["grade"], forward,
            vehicles[trip["vehicle"]]["bpr_alpha"], vehicles[trip["vehicle"]]["bpr_beta"],
            v_over_c.get(link_id, 0),
        )
        touched.append((link_id, forward, segment["payload"] / vehicles[trip["vehicle"]]["capacity_for_resource"], velocity))
        needed = (link["length"] - trip["progress"]) / velocity
        if needed > remaining:
            trip["progress"] += velocity * remaining
            remaining = 0
        else:
            remaining -= needed
            trip["link"] += 1
            trip["progress"] = 0.0
    return touched, trip["segment"] >= len(trip["segments"])


def network_loads(
    network, desire_lines, departures, time_intervals, dwell_times, vehicles,
    vehicle_velocities, vehicle_capacities, road_capacities, alternative_specific_constants, rng,
):
    """Synthesize capacity-constrained, depot-return vehicle tours into
    directional network loads. Every tour carries one resource, serves a
    provider's desire-line endpoints by cheapest insertion, dwells at each
    endpoint, and returns empty to its provider.
    """
    road_capacity = {row["road_type"]: float(row["capacity"]) for row in road_capacities}
    links = []
    for row in network:
        if row["road_type"] not in road_capacity:
            continue
        coordinates = list(row["geometry"].coords)
        links.append({
            "link_id": row["link_id"], "road_type": row["road_type"], "grade": float(row["grade"]),
            "oneway": bool(row["oneway"]), "length": row["geometry"].length,
            "start": coordinates[0], "end": coordinates[-1],
        })
    if not links:
        return []
    node_coordinates = _index_nodes(links)
    nodes = KDTree(node_coordinates)
    links_by_id = {link["link_id"]: link for link in links}
    vehicle_by_name = {row["vehicle"]: {**row, "name": row["vehicle"]} for row in vehicles}
    speeds = defaultdict(dict)
    for row in vehicle_velocities:
        if row["vehicle"] in vehicle_by_name:
            speeds[row["vehicle"]][row["road_type"]] = float(row["velocity"])
    capacities = {(row["vehicle"], row["resource"]): int(row["capacity"]) for row in vehicle_capacities}
    asc = {(row["vehicle"], row["resource"]): float(row["alternative_specific_constant"]) for row in alternative_specific_constants}
    dwell = {row["resource"]: float(row["dwell_time"]) for row in dwell_times}
    intervals = [row["time_interval"] for row in time_intervals]
    durations = {row["time_interval"]: float(row["duration"]) for row in time_intervals}
    shipments = _shipments(desire_lines)
    targets = _targets(desire_lines, departures, intervals)
    active, output, v_over_c = [], [], {}

    for interval in intervals:
        graphs = {
            name: _graph(links, vehicle, speeds[name], vehicle, v_over_c)
            for name, vehicle in vehicle_by_name.items()
        }
        path = _path_cache(graphs, links_by_id, vehicle_by_name, speeds, v_over_c)
        new_trips = []
        for resource in sorted({shipment["resource"] for shipment in shipments}):
            budget = targets.get((resource, interval), 0)
            while budget > 0:
                available = [
                    shipment for shipment in shipments
                    if shipment["resource"] == resource and any(destination["remaining"] > 0 for destination in shipment["destinations"])
                ]
                if not available:
                    break
                shipment = _draw(
                    available,
                    [sum(destination["remaining"] for destination in candidate["destinations"]) for candidate in available],
                    rng,
                )
                seed_index = _draw(
                    [index for index, destination in enumerate(shipment["destinations"]) if destination["remaining"] > 0],
                    [destination["remaining"] for destination in shipment["destinations"] if destination["remaining"] > 0],
                    rng,
                )
                source = nodes.query(shipment["origin"])[1]
                destination_nodes = [nodes.query(destination["point"])[1] for destination in shipment["destinations"]]
                candidates, utilities = [], []
                for name, vehicle in vehicle_by_name.items():
                    capacity = capacities.get((name, resource), 0)
                    if capacity <= 0 or (name, resource) not in asc:
                        continue
                    vehicle["capacity_for_resource"] = capacity
                    candidate = _candidate_tour(
                        shipment, seed_index, source, destination_nodes, vehicle, resource, budget, capacity, path,
                    )
                    if candidate is None:
                        continue
                    candidate["vehicle"] = vehicle
                    candidates.append(candidate)
                    utilities.append(
                        asc[(name, resource)]
                        + vehicle["time_coefficient"] * candidate["time"]
                        + vehicle["distance_coefficient"] * candidate["distance"]
                    )
                if not candidates:
                    shipment["destinations"][seed_index]["remaining"] = 0
                    warnings.warn(
                        f"{resource}: unable to route demand from one provider to a selected recipient",
                        UserWarning,
                    )
                    continue
                candidate = _mnl_choice(candidates, utilities, rng)
                delivered = 0
                for stop in candidate["stops"]:
                    shipment["destinations"][stop["index"]]["remaining"] -= stop["quantity"]
                    delivered += stop["quantity"]
                budget -= delivered
                new_trips.append(_trip(candidate, resource, dwell.get(resource, 0)))

        contributions = defaultdict(lambda: {"count": 0, "velocity": 0.0})
        loads = defaultdict(float)
        still_active = []
        for trip in active + new_trips:
            touched, complete = _advance(trip, durations[interval], links_by_id, speeds, vehicle_by_name, v_over_c)
            for link_id, forward, load_pct, velocity in touched:
                key = (link_id, forward, trip["resource"], trip["vehicle"], load_pct)
                contributions[key]["count"] += 1
                contributions[key]["velocity"] += velocity
                loads[link_id] += vehicle_by_name[trip["vehicle"]]["pcu"]
            if not complete:
                still_active.append(trip)
        active = still_active
        v_over_c = {
            link_id: load / road_capacity[links_by_id[link_id]["road_type"]]
            for link_id, load in loads.items()
        }
        output.extend({
            "link_id": link_id, "time_interval": interval, "resource": resource, "vehicle": vehicle,
            "forward": forward, "vehicle_count": entry["count"], "velocity": entry["velocity"] / entry["count"],
            "load_pct": load_pct,
        } for (link_id, forward, resource, vehicle, load_pct), entry in contributions.items())
    return output
