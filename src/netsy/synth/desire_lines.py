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
    return sorted(column[:-len("_production")] for column in agents.columns if column.endswith("_production"))


def desire_lines(agents, rng):
    """Transactions from producing agents to consuming agents, resource by
    resource. Producers are drawn by remaining production and remain selected
    until depleted; consumers are drawn by remaining consumption and spatial
    proximity. The returned line starts at its provider and ends at its
    consumer.
    """
    agent_ids = agents["agent_id"].tolist()
    points = dict(zip(agent_ids, agents.geometry))
    xs = [point.x for point in points.values()]
    ys = [point.y for point in points.values()]
    scale = math.hypot(max(xs) - min(xs), max(ys) - min(ys)) or 1.0
    rows = []
    transaction_id = 0

    for resource in _resources(agents):
        production = dict(zip(agent_ids, agents[f"{resource}_production"]))
        consumption = dict(zip(agent_ids, agents[f"{resource}_consumption"]))
        production = {agent_id: int(value) if not pd.isna(value) else 0 for agent_id, value in production.items()}
        consumption = {agent_id: int(value) if not pd.isna(value) else 0 for agent_id, value in consumption.items()}

        while True:
            providers = [
                agent_id
                for agent_id, produced in production.items()
                if produced > 0 and any(consumed > 0 and consumer_id != agent_id for consumer_id, consumed in consumption.items())
            ]
            if not providers:
                break
            provider = _pick(providers, [production[agent_id] for agent_id in providers], rng)

            while production[provider] > 0:
                consumers = [agent_id for agent_id, consumed in consumption.items() if consumed > 0 and agent_id != provider]
                if not consumers:
                    break
                consumer = _pick(
                    consumers,
                    [
                        consumption[agent_id] * (1 / (1 + math.exp(points[provider].distance(points[agent_id]) / scale)))
                        for agent_id in consumers
                    ],
                    rng,
                )
                quantity = min(production[provider], consumption[consumer])
                production[provider] -= quantity
                consumption[consumer] -= quantity
                rows.append({
                    "transaction_id": transaction_id,
                    "resource": resource,
                    "quantity": quantity,
                    "origin_agent_id": provider,
                    "destination_agent_id": consumer,
                    "geometry": LineString([points[provider].coords[0], points[consumer].coords[0]]),
                })
                transaction_id += 1

    return geopandas.GeoDataFrame(
        rows,
        columns=[
            "transaction_id", "resource", "quantity", "origin_agent_id",
            "destination_agent_id", "geometry",
        ],
        geometry="geometry",
        crs=agents.crs,
    )
