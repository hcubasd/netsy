import geopandas
import pandas as pd

from netsy.helpers.agent_inputs import combine_agent_inputs
from netsy.helpers.sampling import sample_points, truncated_draw


def _deplete(resources, rng):
    """The (capacity, need) of each resource for every agent of one stratum,
    drawn one agent at a time against the stratum's remaining supply and
    demand until a stop condition holds.

    Each draw truncates the capacity distribution to the remaining supply and
    the need distribution to the remaining demand; capacity and need are
    drawn independently. If any resource has no feasible level, no complete
    agent can be made and generation stops without one. An agent that draws
    zero capacity and need for every resource is kept, but generation stops
    after it, since the state is unchanged and every later round would repeat
    it forever.
    """
    remaining = {name: [resource.supply, resource.demand] for name, resource in resources.items()}
    agents = []
    while True:
        draws = {}
        for name, resource in resources.items():
            capacity = truncated_draw(resource.capacity_levels, resource.capacity_cumulative, remaining[name][0], rng)
            need = truncated_draw(resource.need_levels, resource.need_cumulative, remaining[name][1], rng)
            if capacity is None or need is None:
                return agents
            draws[name] = (capacity, need)
        for name, (capacity, need) in draws.items():
            remaining[name][0] -= capacity
            remaining[name][1] -= need
        agents.append(draws)
        if all(capacity == 0 and need == 0 for capacity, need in draws.values()):
            return agents


def agents(supply, demand, capacities, needs, zones, rng):
    """One row per synthesized agent: `agent_id`, the stratum columns, a
    `{resource}_capacity` and `{resource}_need` for each resource usable in
    its stratum, and a point `geometry` placed uniformly in its zone. The
    number of agents in a stratum is where its depletion stops, not an input.
    `rng` is a numpy Generator, so a seeded one makes the result repeatable.
    Raises ValueError if no agent can be made at all.
    """
    inputs = combine_agent_inputs(supply, demand, capacities, needs, zones)

    frames, xs, ys = [], [], []
    for stratum in inputs.strata:
        drawn = _deplete(stratum.resources, rng)
        if not drawn:
            continue
        x, y = sample_points(stratum.polygon, len(drawn), rng)
        frame = pd.DataFrame({dim: [value] * len(drawn) for dim, value in stratum.dims.items()})
        for name in stratum.resources:
            frame[f"{name}_capacity"] = [agent[name][0] for agent in drawn]
            frame[f"{name}_need"] = [agent[name][1] for agent in drawn]
        frames.append(frame)
        xs.append(x)
        ys.append(y)
    if not frames:
        raise ValueError("no agents could be synthesized from these inputs")

    table = pd.concat(frames, ignore_index=True)
    quantities = [f"{name}_{kind}" for name in inputs.resources for kind in ("capacity", "need") if f"{name}_{kind}" in table.columns]
    table = table[inputs.dims + quantities]
    table[quantities] = table[quantities].astype("Int64")
    table.insert(0, "agent_id", range(1, len(table) + 1))

    points = geopandas.points_from_xy(pd.concat([pd.Series(x) for x in xs]), pd.concat([pd.Series(y) for y in ys]))
    return geopandas.GeoDataFrame(table, geometry=points, crs=zones.crs)
