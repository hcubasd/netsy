"""Synthesize shipments between agents, facilities and zones, as MASS-GT's
shipment synthesis (SHIP) does, generalized to any resources, regions, flow
types and facility types.

Every row of the shipment totals is a quantity of one shipment stratum (a
resource and any other dimensions, such as a logistic segment) to move from
one region to another by one flow type. A flow type names what each end is:
an agent, a facility of some type, or a zone itself. Shipments are drawn one
at a time until the quantity is moved. The end that is not decayed is drawn
first, an agent by its size times its production or consumption rate, a
facility by a weight column; the other end is drawn by the same weight times
MASS-GT's distance decay, 1 / (1 + exp(alpha + beta ln cost)), on the cost
of the trip between the two zones. Each shipment's size class and vehicle are
then chosen jointly by multinomial logit, it carries its class's quantity or
whatever is left, and, after all shipments are drawn, its delivery window is
chosen by a second multinomial logit.
"""

import geopandas
import numpy as np
import pandas as pd
from shapely.geometry import LineString

from netsy.helpers.validate import SHIPMENT_TOTAL_FIELDS
from netsy.synth.agents import _zone_key

# Kinds of shipment end that are not facility types.
AGENT, ZONE = "agent", "zone"


def _text(value):
    return None if value is None or (isinstance(value, float) and np.isnan(value)) else _zone_key(value)


def _rows_for(table, keys, stratum):
    """The rows of `table` whose `keys` match `stratum`."""
    mask = np.ones(len(table), dtype=bool)
    for key in keys:
        mask &= table[key].map(_text).to_numpy() == stratum[key]
    return table[mask]


def _keys(table, values, columns, name, allowed):
    keys = [column for column in table.columns if column not in values]
    extra = sorted(set(keys) - set(allowed))
    if extra:
        raise ValueError(f"{name}: columns {extra} are not {columns}")
    return keys


def _pick(cumulative, rng):
    """An index drawn by the cumulative weights `cumulative`."""
    index = int(np.searchsorted(cumulative, rng.random() * cumulative[-1], side="right"))
    return min(index, len(cumulative) - 1)


class _Ends:
    """The candidates for one end of a shipment: who they are, the skim index
    of their zone, their weight and their location. Draws by weight alone,
    or by weight times a decay per zone, drawing a zone first and then a
    candidate within it, which is the same draw made in fewer steps.
    """

    def __init__(self, kind, ids, zones, weights, points, rows=None):
        self.kind, self.ids, self.zones, self.points, self.rows = kind, ids, zones, points, rows
        self.weights = np.asarray(weights, dtype=float)
        self.cumulative = np.cumsum(self.weights)
        order = np.argsort(zones, kind="stable")
        self.zone_ids, starts = np.unique(zones[order], return_index=True)
        self.members = np.split(order, starts[1:])
        self.zone_weights = np.add.reduceat(self.weights[order], starts)

    def total(self):
        return self.cumulative[-1]

    def draw(self, rng):
        return _pick(self.cumulative, rng)

    def draw_near(self, decay, rng):
        weights = self.zone_weights * decay[self.zone_ids]
        if not weights.sum() > 0:
            return None
        members = self.members[_pick(np.cumsum(weights), rng)]
        return members[_pick(np.cumsum(self.weights[members]), rng)]

    def subset(self, mask):
        indices = np.flatnonzero(mask & (self.weights > 0))
        if not len(indices):
            return None
        return _Ends(
            self.kind, self.ids[indices], self.zones[indices], self.weights[indices], self.points[indices],
            None if self.rows is None else self.rows.iloc[indices],
        )


def _choice_terms(table, alternatives, column, stratum, keys, name):
    """`(term, values)` pairs: per term of the rows matching `stratum`, its
    value for every alternative, where an empty alternative cell means every
    alternative.
    """
    rows = _rows_for(table, keys, stratum)
    if rows.empty:
        raise ValueError(f"{name}: no coefficients for {_label(stratum, keys)}")
    terms = {}
    for row in rows.to_dict("records"):
        values = terms.setdefault(row["term"], np.zeros(len(alternatives)))
        alternative = _text(row[column])
        if alternative is None:
            values += row["value"]
        else:
            matches = alternatives == alternative
            if not matches.any():
                raise ValueError(f"{name}: {column} {alternative!r} is not defined")
            values[matches] += row["value"]
    return terms


def _label(stratum, keys=None):
    return {key: stratum[key] for key in (stratum if keys is None else keys)}


def _logit(utilities, rng):
    """An alternative drawn by multinomial logit on `utilities`."""
    weights = np.exp(utilities - utilities.max())
    return _pick(np.cumsum(weights), rng)


class _VehicleChoice:
    """The joint size-class and vehicle multinomial logit of one stratum, as
    MASS-GT specifies it: per alternative, a constant, the transport cost of
    the vehicles needed, the shipment's size, and indicators of each end's
    kind and of the trip's distance being above a threshold.
    """

    TERMS = "constant, transport_cost, size, size_class:<class>, origin:<kind>, destination:<kind>, distance_above:<km>"

    def __init__(self, sizes, vehicles, table, stratum, keys):
        size_count, vehicle_count = len(sizes), len(vehicles)
        self.size_classes = np.repeat(sizes["size_class"].map(_text).to_numpy(), vehicle_count)
        self.quantities = np.repeat(sizes["quantity"].to_numpy(dtype=float), vehicle_count)
        self.vehicles = np.tile(vehicles["vehicle"].map(_text).to_numpy(), size_count)
        capacity = np.tile(vehicles["capacity"].to_numpy(dtype=float), size_count)
        self.cost_per_hour = np.tile(vehicles["cost_per_hour"].to_numpy(dtype=float), size_count)
        self.cost_per_km = np.tile(vehicles["cost_per_km"].to_numpy(dtype=float), size_count)
        self.vehicles_needed = np.ceil(self.quantities / capacity)

        terms = _choice_terms(table, self.vehicles, "vehicle", stratum, keys, "vehicle_choice.csv")
        self.constant = np.zeros(len(self.vehicles))
        self.transport_cost = np.zeros(len(self.vehicles))
        self.ends, self.distances = [], []
        for term, values in terms.items():
            name, _, argument = term.partition(":")
            if term == "constant":
                self.constant += values
            elif term == "size":
                self.constant += values * self.quantities
            elif term == "transport_cost":
                self.transport_cost += values
            elif name == "size_class" and argument:
                self.constant += values * (self.size_classes == argument)
            elif name in ("origin", "destination") and argument:
                self.ends.append((name, argument, values))
            elif name == "distance_above" and _number(argument) is not None:
                self.distances.append((_number(argument), values))
            else:
                raise ValueError(f"vehicle_choice.csv: unknown term {term!r}; terms are {self.TERMS}")

    def choose(self, time, distance, origin_kind, destination_kind, rng):
        costs = (self.cost_per_hour * time + self.cost_per_km * distance) * self.vehicles_needed
        utilities = self.constant + self.transport_cost * costs
        for end, kind, values in self.ends:
            if (origin_kind if end == "origin" else destination_kind) == kind:
                utilities = utilities + values
        for threshold, values in self.distances:
            if distance > threshold:
                utilities = utilities + values
        index = _logit(utilities, rng)
        return self.size_classes[index], self.quantities[index], self.vehicles[index]


def _ids(values):
    """Ids with gaps, as whole numbers where every id is one."""
    try:
        return pd.array(values, dtype="Int64")
    except (TypeError, ValueError):
        return pd.array(values, dtype=object)


def _number(text):
    try:
        return float(text)
    except ValueError:
        return None


def _intrazonal(matrix):
    """`matrix` with values below zero as zero, and each zero, such as an
    intrazonal cell, as half the smallest positive value of its row, as
    MASS-GT fills its skims.
    """
    matrix[matrix < 0] = 0
    smallest = np.where(matrix > 0, matrix, np.inf).min(axis=1)
    rows, columns = np.nonzero(matrix == 0)
    matrix[rows, columns] = np.where(np.isfinite(smallest[rows]), smallest[rows] / 2, 0)
    return matrix


def shipments(
    zones, agents, facilities, skims, production_rates, consumption_rates, shipment_totals, flow_types,
    distance_decay, shipment_sizes, shipment_vehicles, vehicle_choice, delivery_windows, delivery_choice, rng,
):
    """One row per synthesized shipment: `transaction_id`, its stratum
    columns, `quantity`, `flow_type`, the agent, facility and zone of each
    end, its `size_class`, `vehicle` and delivery `window` with its
    `window_start` and `window_end`, and a line from its origin to its
    destination. `facilities` may be None when no flow type uses one, and
    the delivery tables both None to choose no window; `skims` is
    `(zone_ids, time, distance)`. `rng` is a numpy Generator, so a seeded one makes the result
    repeatable. Raises ValueError if the tables do not fit together.
    """
    if "region" not in zones.columns:
        raise ValueError("zones.gpkg: missing 'region' column, the region each zone belongs to")
    zone_ids, time, distance = skims
    skim_index = {zone: index for index, zone in enumerate(zone_ids)}
    zone_keys = zones["zone_id"].map(_zone_key)
    missing = sorted(set(zone_keys) - set(skim_index))
    if missing:
        raise ValueError(f"skims.omx: zones {missing[:5]}{'...' if len(missing) > 5 else ''} of zones.gpkg are not in the skims")
    time, distance = _intrazonal(np.array(time, dtype=np.float32)), _intrazonal(np.array(distance, dtype=np.float32))
    zone_index = zone_keys.map(skim_index).to_numpy()
    zone_region = dict(zip(zone_keys, zones["region"].map(_zone_key)))
    zone_regions = zones["region"].map(_zone_key).to_numpy()
    known_regions = set(zone_regions)
    zone_original = dict(zip(zone_keys, zones["zone_id"]))
    zone_points = zones.geometry.representative_point()
    zone_points = np.array(list(zip(zone_points.x, zone_points.y)))
    zone_columns = {}

    def zone_column(column, name):
        if column not in zone_columns:
            if column not in zones.columns:
                raise ValueError(f"{name}: zones.gpkg has no column {column!r}")
            values = pd.to_numeric(zones[column], errors="coerce")
            if values.isna().any():
                raise ValueError(f"zones.gpkg: '{column}' must hold numbers in every row")
            by_skim = np.zeros(len(zone_ids))
            by_skim[zone_index] = values.to_numpy(dtype=float)
            zone_columns[column] = by_skim
        return zone_columns[column]

    def zones_of(table, name):
        keys = table["zone_id"].map(_zone_key)
        unknown = sorted(set(keys) - set(zone_region))
        if unknown:
            raise ValueError(f"{name}: zones {unknown[:5]} are not in zones.gpkg")
        return keys

    agent_zones = zones_of(agents, "agents.gpkg")
    agent_regions = agent_zones.map(zone_region).to_numpy()
    agent_strata = [column for column in agents.columns if column not in ("agent_id", "size", "geometry")]
    agent_text = pd.DataFrame({column: agents[column].map(_zone_key) for column in agent_strata})
    agent_points = np.array(list(zip(agents.geometry.x, agents.geometry.y)))
    if facilities is not None:
        facility_zones = zones_of(facilities, "facilities.gpkg")
        facility_points = np.array(list(zip(facilities.geometry.x, facilities.geometry.y)))
        facility_types = facilities["facility_type"].map(_zone_key)
        facility_regions = facility_zones.map(zone_region).to_numpy()

    strata = [column for column in shipment_totals.columns if column not in SHIPMENT_TOTAL_FIELDS]
    for name, table in (("production_rates.csv", production_rates), ("consumption_rates.csv", consumption_rates)):
        _keys(table, ("rate",), "agent or shipment stratum columns", name, agent_strata + strata)
    decay_keys = _keys(
        distance_decay, ("alpha", "beta", "cost_per_hour", "cost_per_km"), "shipment stratum columns",
        "distance_decay.csv", strata,
    )
    vehicle_keys = _keys(vehicle_choice, ("vehicle", "term", "value"), "shipment stratum columns", "vehicle_choice.csv", strata)
    if (delivery_windows is None) != (delivery_choice is None):
        raise ValueError("delivery_windows.csv and delivery_choice.csv: give both, or neither")
    if delivery_windows is not None:
        window_keys = _keys(delivery_windows, ("window", "start", "end"), "shipment stratum columns", "delivery_windows.csv", strata)
        delivery_keys = _keys(delivery_choice, ("window", "term", "value"), "shipment stratum columns", "delivery_choice.csv", strata)
    flows = {_zone_key(row["flow_type"]): row for row in flow_types.to_dict("records")}

    ends_cache, rate_cache, decay_cache, vehicle_cache = {}, {}, {}, {}

    def agent_weights(rates, name, stratum):
        rate_keys = [column for column in rates.columns if column != "rate"]
        on_agents = [column for column in rate_keys if column in agent_strata]
        on_strata = [column for column in rate_keys if column not in agent_strata]
        cache_key = (name, tuple(stratum[column] for column in on_strata))
        if cache_key not in rate_cache:
            rows = _rows_for(rates, on_strata, stratum)
            if on_agents:
                lookup = {tuple(_zone_key(row[column]) for column in on_agents): row["rate"] for row in rows.to_dict("records")}
                keys = agent_text[on_agents].itertuples(index=False, name=None)
                rate = np.array([lookup.get(key, 0.0) for key in keys], dtype=float)
            else:
                rate = np.full(len(agents), rows["rate"].sum())
            rate_cache[cache_key] = agents["size"].to_numpy(dtype=float) * rate
        return rate_cache[cache_key]

    def ends(kind, region, zone, weight, stratum, side):
        rates, name = (production_rates, "production") if side == "origin" else (consumption_rates, "consumption")
        rate_part = tuple(stratum.values()) if kind == AGENT else ()
        cache_key = (kind, region, zone, weight, side, rate_part)
        if cache_key in ends_cache:
            return ends_cache[cache_key]
        where = f"{side} region {region!r}" + (f", zone {zone!r}" if zone is not None else "")
        if kind == ZONE:
            mask = (zone_regions == region) & ((zone_keys == zone).to_numpy() if zone else True)
            found = _Ends(ZONE, zone_keys[mask].to_numpy(), zone_index[mask], np.ones(mask.sum()), zone_points[mask])
            if not mask.any():
                raise ValueError(f"shipment_totals.csv: no zone in {where}")
        elif kind == AGENT:
            mask = (agent_regions == region) & ((agent_zones == zone).to_numpy() if zone else True)
            weights = agent_weights(rates, f"{name}_rates.csv", stratum)[mask]
            found = _Ends(AGENT, agents["agent_id"].to_numpy()[mask], agent_zones[mask].map(skim_index).to_numpy(), weights, agent_points[mask])
            if not weights.sum() > 0:
                raise ValueError(f"{name}_rates.csv: no agent in {where} has a {name} of {_label(stratum)}")
        else:
            if facilities is None:
                raise ValueError(f"flow_types.csv: facility type {kind!r} needs facilities.gpkg")
            column = weight or "size"
            mask = np.array(facility_types == kind)
            if not mask.any():
                raise ValueError(f"flow_types.csv: no facility in facilities.gpkg has type {kind!r}")
            if column not in facilities.columns:
                raise ValueError(f"facilities.gpkg: missing weight column {column!r}")
            weights = pd.to_numeric(facilities[column], errors="coerce").to_numpy(dtype=float)
            if np.isnan(weights[mask]).any() or (weights[mask] < 0).any():
                raise ValueError(f"facilities.gpkg: '{column}' must hold numbers of at least 0 for every {kind!r}")
            mask &= (facility_regions == region) & ((facility_zones == zone).to_numpy() if zone else True)
            found = _Ends(
                kind, facilities["facility_id"].to_numpy()[mask], facility_zones[mask].map(skim_index).to_numpy(),
                weights[mask], facility_points[mask], facilities[mask].reset_index(drop=True),
            )
            if not found.weights.sum() > 0:
                raise ValueError(f"facilities.gpkg: no {kind!r} with a {column!r} above 0 in {where}")
        ends_cache[cache_key] = found
        return found

    def decay_for(stratum):
        rows = _rows_for(distance_decay, decay_keys, stratum)
        if rows.empty:
            raise ValueError(f"distance_decay.csv: no parameters for {_label(stratum, decay_keys)}")
        row = rows.iloc[0]
        key = (row["alpha"], row["beta"], row["cost_per_hour"], row["cost_per_km"])
        if key not in decay_cache:
            cost = np.float32(row["cost_per_hour"]) * time + np.float32(row["cost_per_km"]) * distance
            with np.errstate(divide="ignore", over="ignore"):
                decay_cache[key] = 1 / (1 + np.exp(np.float32(row["alpha"]) + np.float32(row["beta"]) * np.log(cost)))
        return decay_cache[key]

    def vehicle_choice_for(stratum):
        key = tuple(stratum[column] for column in vehicle_keys)
        if key not in vehicle_cache:
            vehicle_cache[key] = _VehicleChoice(shipment_sizes, shipment_vehicles, vehicle_choice, stratum, vehicle_keys)
        return vehicle_cache[key]

    def constrain(flow, second, first, chosen):
        """`second` restricted, by the flow type, to candidates that may go
        with candidate `chosen` of `first`.
        """
        mask = np.ones(len(second.ids), dtype=bool)
        if flow["same"] is not None and not pd.isna(flow["same"]):
            column = flow["same"]
            if first.rows is None or second.rows is None:
                raise ValueError(f"flow_types.csv: flow type {flow['flow_type']!r} needs facilities at both ends for 'same'")
            if column not in second.rows.columns:
                raise ValueError(f"facilities.gpkg: missing column {column!r}")
            mask &= (second.rows[column] == first.rows[column].iloc[chosen]).to_numpy()
        if flow["distinct"]:
            mask &= second.ids != first.ids[chosen]
        if mask.all():
            return second
        return second.subset(mask)

    columns = {
        "stratum": [], "quantity": [], "flow_type": [], "origin": [], "destination": [],
        "size_class": [], "vehicle": [], "origin_skim": [], "destination_skim": [],
    }
    for row in shipment_totals.to_dict("records"):
        total = row["quantity"]
        if total <= 0:
            continue
        flow_name = _zone_key(row["flow_type"])
        if flow_name not in flows:
            raise ValueError(f"shipment_totals.csv: flow type {flow_name!r} is not in flow_types.csv")
        flow = flows[flow_name]
        stratum = {column: _zone_key(row[column]) for column in strata}
        regions = {side: _zone_key(row[f"{side}_region"]) for side in ("origin", "destination")}
        pinned = {side: _text(row.get(f"{side}_zone_id")) for side in ("origin", "destination")}
        for side in ("origin", "destination"):
            if pinned[side] is not None and zone_region.get(pinned[side]) != regions[side]:
                raise ValueError(f"shipment_totals.csv: zone {pinned[side]!r} is not in {side} region {regions[side]!r}")
        if not set(regions.values()) <= known_regions:
            raise ValueError(f"shipment_totals.csv: regions {sorted(regions.values())} must be regions of zones.gpkg")
        origin, destination = (
            ends(_zone_key(flow[side]), regions[side], pinned[side], _text(flow[f"{side}_weight"]), stratum, side)
            for side in ("origin", "destination")
        )
        decayed = _text(flow["decay"])
        decay = decay_for(stratum) if decayed else None
        choice = vehicle_choice_for(stratum)

        moved = 0.0
        while moved < total:
            # The end that is not decayed is drawn first; without decay, the
            # destination is, as MASS-GT draws the receiver first.
            if decayed == "destination":
                origin_end, o = origin, origin.draw(rng)
                destination_end = constrain(flow, destination, origin, o)
                d = None if destination_end is None else destination_end.draw_near(decay[origin.zones[o], :], rng)
                second = d
            else:
                destination_end, d = destination, destination.draw(rng)
                origin_end = constrain(flow, origin, destination, d)
                if origin_end is None:
                    o = None
                elif decayed == "origin":
                    o = origin_end.draw_near(decay[:, destination.zones[d]], rng)
                else:
                    o = origin_end.draw(rng)
                second = o
            if second is None:
                side = decayed or "origin"
                raise ValueError(
                    f"shipment_totals.csv: no {flow[side]!r} {side} can be paired by flow type {flow_name!r} "
                    f"for {_label(stratum)}"
                )
            origin_skim, destination_skim = origin_end.zones[o], destination_end.zones[d]
            size_class, size, vehicle = choice.choose(
                float(time[origin_skim, destination_skim]), float(distance[origin_skim, destination_skim]),
                origin_end.kind, destination_end.kind, rng,
            )
            quantity = min(size, total - moved)
            moved += quantity
            for name, value in (
                ("stratum", tuple(stratum.values())), ("quantity", quantity), ("flow_type", flow_name),
                ("origin", (origin_end, o)), ("destination", (destination_end, d)), ("size_class", size_class),
                ("vehicle", vehicle), ("origin_skim", origin_skim), ("destination_skim", destination_skim),
            ):
                columns[name].append(value)

    count = len(columns["quantity"])
    if not count:
        raise ValueError("shipment_totals.csv: no quantity to ship")
    table = pd.DataFrame(columns["stratum"], columns=strata)
    table.insert(0, "transaction_id", range(1, count + 1))
    table.insert(table.columns.get_loc("resource") + 1, "quantity", columns["quantity"])
    points = {}
    for side in ("origin", "destination"):
        found = columns[side]
        table[f"{side}_agent_id"] = _ids([end.ids[i] if end.kind == AGENT else None for end, i in found])
    table["flow_type"] = columns["flow_type"]
    skim_zone = {index: zone_original[zone] for zone, index in skim_index.items() if zone in zone_original}
    for side in ("origin", "destination"):
        table[f"{side}_facility_id"] = [end.ids[i] if end.kind not in (AGENT, ZONE) else None for end, i in columns[side]]
    for side in ("origin", "destination"):
        table[f"{side}_zone_id"] = [skim_zone[index] for index in columns[f"{side}_skim"]]
        points[side] = [end.points[i] for end, i in columns[side]]
    table["size_class"] = columns["size_class"]
    table["vehicle"] = columns["vehicle"]
    if delivery_windows is not None:
        _delivery_windows(
            table, strata, columns, delivery_windows, window_keys, delivery_choice, delivery_keys, zone_column, rng,
        )
    lines = [LineString([tuple(a), tuple(b)]) for a, b in zip(points["origin"], points["destination"])]
    return geopandas.GeoDataFrame(table, geometry=lines, crs=zones.crs)


def _delivery_windows(table, strata, columns, windows, window_keys, choice, choice_keys, zone_column, rng):
    """Add each shipment's delivery `window`, `start` and `end` to `table`,
    chosen by multinomial logit over its stratum's windows: per window, a
    constant, the log of its duration, numeric zone columns at either end,
    and indicators of the shipment's vehicle.
    """
    chosen = np.empty(len(table), dtype=object)
    starts, ends = np.zeros(len(table)), np.zeros(len(table))
    origin_skim, destination_skim = np.array(columns["origin_skim"]), np.array(columns["destination_skim"])
    vehicles = table["vehicle"].to_numpy()
    groups = table.groupby(strata, sort=False).indices if strata else {(): np.arange(len(table))}
    for key, positions in groups.items():
        stratum = dict(zip(strata, key if isinstance(key, tuple) else (key,)))
        rows = _rows_for(windows, window_keys, stratum)
        if rows.empty:
            raise ValueError(f"delivery_windows.csv: no windows for {_label(stratum, window_keys)}")
        names = rows["window"].map(_text).to_numpy()
        terms = _choice_terms(choice, names, "window", stratum, choice_keys, "delivery_choice.csv")
        utilities = np.zeros((len(positions), len(names)))
        for term, values in terms.items():
            name, _, argument = term.partition(":")
            if term == "constant":
                utilities += values
            elif term == "log_duration":
                utilities += values * np.log((rows["end"] - rows["start"]).to_numpy(dtype=float))
            elif name in ("origin", "destination") and argument:
                skims = origin_skim if name == "origin" else destination_skim
                utilities += np.outer(zone_column(argument, "delivery_choice.csv")[skims[positions]], values)
            elif name == "vehicle" and argument:
                utilities += np.outer(vehicles[positions] == argument, values)
            else:
                raise ValueError(
                    f"delivery_choice.csv: unknown term {term!r}; terms are constant, log_duration, "
                    "origin:<zone column>, destination:<zone column>, vehicle:<vehicle>"
                )
        weights = np.exp(utilities - utilities.max(axis=1, keepdims=True))
        cumulative = np.cumsum(weights, axis=1)
        draws = rng.random(len(positions))[:, None] * cumulative[:, -1:]
        picks = np.minimum((cumulative <= draws).sum(axis=1), len(names) - 1)
        chosen[positions] = names[picks]
        starts[positions] = rows["start"].to_numpy(dtype=float)[picks]
        ends[positions] = rows["end"].to_numpy(dtype=float)[picks]
    table["window"] = chosen
    table["window_start"] = starts
    table["window_end"] = ends
