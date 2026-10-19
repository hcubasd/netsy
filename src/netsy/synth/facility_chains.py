"""Turn direct transactions into ordered legs through explicit facilities."""

from __future__ import annotations

import geopandas
import pandas as pd
from shapely.geometry import LineString


_TRANSACTION_COLUMNS = {
    "transaction_id",
    "resource",
    "quantity",
    "origin_agent_id",
    "destination_agent_id",
}
_FACILITY_COLUMNS = {"facility_id", "facility_type", "capacity"}
_STEP_COLUMNS = {"transaction_id", "sequence", "facility_id"}


def _check_transactions(transactions):
    missing = _TRANSACTION_COLUMNS - set(transactions.columns)
    if missing:
        raise ValueError(f"transactions: missing columns {sorted(missing)}")
    if transactions.crs is None:
        raise ValueError("transactions: missing CRS")
    if transactions.geometry.isna().any() or not transactions.geometry.geom_type.eq("LineString").all():
        raise ValueError("transactions: every geometry must be a line")
    if transactions["transaction_id"].isna().any() or transactions["transaction_id"].duplicated().any():
        raise ValueError("transactions: 'transaction_id' values must be present and unique")
    quantities = pd.to_numeric(transactions["quantity"], errors="coerce")
    if quantities.isna().any() or (quantities <= 0).any() or (quantities % 1 != 0).any():
        raise ValueError("transactions: 'quantity' must contain positive whole numbers")


def _check_facilities(facilities, crs):
    missing = _FACILITY_COLUMNS - set(facilities.columns)
    if missing:
        raise ValueError(f"facilities: missing columns {sorted(missing)}")
    if facilities.crs != crs:
        raise ValueError("facilities: CRS must match transactions")
    if facilities.geometry.isna().any() or not facilities.geometry.geom_type.eq("Point").all():
        raise ValueError("facilities: every geometry must be a point")
    if facilities["facility_id"].isna().any() or facilities["facility_id"].duplicated().any():
        raise ValueError("facilities: 'facility_id' values must be present and unique")
    if facilities["facility_type"].isna().any():
        raise ValueError("facilities: 'facility_type' values must be present")
    capacity = pd.to_numeric(facilities["capacity"], errors="coerce")
    if capacity.isna().any() or (capacity < 0).any() or (capacity % 1 != 0).any():
        raise ValueError("facilities: 'capacity' must contain whole numbers, zero or more")


def _check_steps(steps, transaction_ids, facility_ids):
    missing = _STEP_COLUMNS - set(steps.columns)
    if missing:
        raise ValueError(f"facility chain steps: missing columns {sorted(missing)}")
    if steps.empty:
        return
    sequences = pd.to_numeric(steps["sequence"], errors="coerce")
    if sequences.isna().any() or (sequences < 1).any() or (sequences % 1 != 0).any():
        raise ValueError("facility chain steps: 'sequence' must contain whole numbers, one or more")
    if not set(steps["transaction_id"]).issubset(transaction_ids):
        raise ValueError("facility chain steps: every transaction_id must exist in transactions")
    if not set(steps["facility_id"]).issubset(facility_ids):
        raise ValueError("facility chain steps: every facility_id must exist in facilities")
    if steps.duplicated(["transaction_id", "sequence"]).any():
        raise ValueError("facility chain steps: each transaction_id and sequence pair must be unique")
    for transaction_id, group in steps.groupby("transaction_id", sort=False):
        expected = list(range(1, len(group) + 1))
        actual = sorted(group["sequence"].astype(int).tolist())
        if actual != expected:
            raise ValueError(
                f"facility chain steps: transaction {transaction_id!r} sequences must start at one and be consecutive"
            )


def facility_chains(transactions, facilities, steps):
    """Expand transactions into direct or facility-mediated movement legs.

    Facilities are scenario data rather than named model branches. A package
    that passes through a UCC or microhub is represented by ordered facility
    steps for its transaction. Facility capacity is consumed by throughput,
    making infeasible scenarios fail explicitly instead of silently routing
    through an overloaded facility.
    """
    _check_transactions(transactions)
    _check_facilities(facilities, transactions.crs)
    _check_steps(
        steps,
        set(transactions["transaction_id"]),
        set(facilities["facility_id"]),
    )

    facility_points = facilities.set_index("facility_id").geometry.to_dict()
    facility_types = facilities.set_index("facility_id")["facility_type"].to_dict()
    remaining_capacity = {
        facility_id: int(capacity)
        for facility_id, capacity in facilities.set_index("facility_id")["capacity"].items()
    }
    steps_by_transaction = {
        transaction_id: group.sort_values("sequence").to_dict("records")
        for transaction_id, group in steps.groupby("transaction_id", sort=False)
    }
    rows = []

    for transaction in transactions.to_dict("records"):
        transaction_id = transaction["transaction_id"]
        quantity = int(transaction["quantity"])
        chain = steps_by_transaction.get(transaction_id, [])
        for step in chain:
            facility_id = step["facility_id"]
            if remaining_capacity[facility_id] < quantity:
                raise ValueError(
                    f"facility {facility_id!r}: capacity is insufficient for transaction {transaction_id!r}"
                )
            remaining_capacity[facility_id] -= quantity

        origin, destination = list(transaction["geometry"].coords)[0], list(transaction["geometry"].coords)[-1]
        locations = [origin] + [facility_points[step["facility_id"]].coords[0] for step in chain] + [destination]
        actor_ids = (
            [transaction["origin_agent_id"]]
            + [f"facility:{step['facility_id']}" for step in chain]
            + [transaction["destination_agent_id"]]
        )
        location_ids = (
            [f"agent:{transaction['origin_agent_id']}"]
            + [f"facility:{step['facility_id']}" for step in chain]
            + [f"agent:{transaction['destination_agent_id']}"]
        )
        for position, (start, end) in enumerate(zip(locations, locations[1:]), start=1):
            entering = chain[position - 1]["facility_id"] if position <= len(chain) else None
            leaving = chain[position - 2]["facility_id"] if position > 1 else None
            rows.append(
                {
                    "transaction_id": transaction_id,
                    "leg_id": f"{transaction_id}:{position}",
                    "sequence": position,
                    "resource": transaction["resource"],
                    "quantity": quantity,
                    "origin_agent_id": actor_ids[position - 1],
                    "destination_agent_id": actor_ids[position],
                    "origin_location_id": location_ids[position - 1],
                    "destination_location_id": location_ids[position],
                    "origin_facility_type": facility_types.get(leaving),
                    "destination_facility_type": facility_types.get(entering),
                    "geometry": LineString([start, end]),
                }
            )

    return geopandas.GeoDataFrame(rows, geometry="geometry", crs=transactions.crs)
