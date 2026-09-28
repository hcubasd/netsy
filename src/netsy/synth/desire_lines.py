import math

import geopandas
import numpy as np
import pandas as pd
from shapely.geometry import LineString


def _pick(items, weights, rng):
    probabilities = np.asarray(weights, dtype=float)
    probabilities /= probabilities.sum()
    return items[rng.choice(len(items), p=probabilities)]


def _resources(agents):
    return sorted(column[:-len("_capacity")] for column in agents.columns if column.endswith("_capacity"))


def desire_lines(agents, rng):
    """Transactions from capacity providers to need consumers, resource by
    resource. Providers are drawn by remaining capacity and remain selected
    until depleted; consumers are drawn by remaining need and spatial
    proximity. The returned line starts at its provider and ends at its
    consumer.
    """
    agent_ids = agents["agent_id"].tolist()
    points = dict(zip(agent_ids, agents.geometry))
    xs = [point.x for point in points.values()]
    ys = [point.y for point in points.values()]
    scale = math.hypot(max(xs) - min(xs), max(ys) - min(ys)) or 1.0
    rows = []

    for resource in _resources(agents):
        capacities = dict(zip(agent_ids, agents[f"{resource}_capacity"]))
        needs = dict(zip(agent_ids, agents[f"{resource}_need"]))
        capacities = {agent_id: int(value) if not pd.isna(value) else 0 for agent_id, value in capacities.items()}
        needs = {agent_id: int(value) if not pd.isna(value) else 0 for agent_id, value in needs.items()}

        while True:
            providers = [
                agent_id
                for agent_id, capacity in capacities.items()
                if capacity > 0 and any(need > 0 and consumer_id != agent_id for consumer_id, need in needs.items())
            ]
            if not providers:
                break
            provider = _pick(providers, [capacities[agent_id] for agent_id in providers], rng)

            while capacities[provider] > 0:
                consumers = [agent_id for agent_id, need in needs.items() if need > 0 and agent_id != provider]
                if not consumers:
                    break
                consumer = _pick(
                    consumers,
                    [
                        needs[agent_id] * (1 / (1 + math.exp(points[provider].distance(points[agent_id]) / scale)))
                        for agent_id in consumers
                    ],
                    rng,
                )
                quantity = min(capacities[provider], needs[consumer])
                capacities[provider] -= quantity
                needs[consumer] -= quantity
                rows.append({
                    "resource": resource,
                    "quantity": quantity,
                    "origin_agent_id": provider,
                    "geometry": LineString([points[provider].coords[0], points[consumer].coords[0]]),
                })

    return geopandas.GeoDataFrame(
        rows,
        columns=["resource", "quantity", "origin_agent_id", "geometry"],
        geometry="geometry",
        crs=agents.crs,
    )
