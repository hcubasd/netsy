import pandas as pd


def check_agents(agents):
    """Raise ValueError unless `agents` has unique identifiers, point
    locations, and paired whole-number capacity/need resource columns.
    Empty resource values are permitted: they mean that agent does not
    participate in that resource.
    """
    if "agent_id" not in agents.columns:
        raise ValueError("missing 'agent_id' column")
    if agents.empty:
        raise ValueError("must have at least one row")
    if agents["agent_id"].isna().any() or agents["agent_id"].duplicated().any():
        raise ValueError("'agent_id' values must be present and unique")
    if agents.crs is None:
        raise ValueError("missing CRS")
    if agents.geometry.isna().any() or agents.geometry.is_empty.any():
        raise ValueError("every agent needs a geometry")
    if not agents.geometry.geom_type.eq("Point").all():
        raise ValueError("agent geometries must be points")

    capacities = {column[:-len("_capacity")] for column in agents.columns if column.endswith("_capacity")}
    needs = {column[:-len("_need")] for column in agents.columns if column.endswith("_need")}
    if not capacities:
        raise ValueError("must have at least one paired capacity and need resource")
    if capacities != needs:
        raise ValueError("every resource must have both '_capacity' and '_need' columns")
    for resource in capacities:
        for suffix in ("_capacity", "_need"):
            values = pd.to_numeric(agents[f"{resource}{suffix}"], errors="coerce")
            original = agents[f"{resource}{suffix}"]
            if original.notna().ne(values.notna()).any() or ((values.dropna() < 0) | (values.dropna() % 1 != 0)).any():
                raise ValueError(f"'{resource}{suffix}' must contain whole numbers, zero or more, or empty cells")
