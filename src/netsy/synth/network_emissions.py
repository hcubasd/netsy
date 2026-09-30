import bisect


GRADIENT_BINS = (-6, -4, -2, 0, 2, 4, 6)
PAYLOAD_BINS = (0, 50, 100)


def _snap(value, bins):
    index = bisect.bisect_left(bins, value)
    if index == 0:
        return bins[0]
    if index == len(bins):
        return bins[-1]
    before, after = bins[index - 1], bins[index]
    return before if abs(value - before) <= abs(value - after) else after


def _hot_emission_factor(coefficients, velocity):
    """COPERT V's hot-exhaust factor in grams per kilometre."""
    if velocity <= 0:
        return None
    denominator = (
        coefficients["epsilon"] * velocity ** 2
        + coefficients["zeta"] * velocity
        + coefficients["eta"]
    )
    if denominator == 0:
        return None
    numerator = (
        coefficients["alpha"] * velocity ** 2
        + coefficients["beta"] * velocity
        + coefficients["gamma"]
        + coefficients["delta"] / velocity
    )
    return max(0.0, numerator / denominator * (1 - coefficients["rf"]))


def network_emissions(network_loads, network, vehicles, copert_coefficients, emission_factors):
    """Calculate separate COPERT V hot-exhaust and flat non-exhaust grams
    for every network-load stratum. Geometry lengths must be kilometres.
    """
    links = {row["link_id"]: {"grade": float(row["grade"]), "length": row["geometry"].length} for row in network}
    vehicle_types = {row["vehicle"]: row["vehicle_type"] for row in vehicles}
    coefficients = {
        (row["vehicle_type"], row["pollutant"], row["gradient_bin"], row["payload_bin"]): row
        for row in copert_coefficients
    }
    pollutants = {}
    for row in copert_coefficients:
        pollutants.setdefault(row["vehicle_type"], set()).add(row["pollutant"])
    non_exhaust = {
        (row["vehicle_type"], row["pollutant"]): float(row["emission_factor"])
        for row in emission_factors
    }

    output = []
    for load in network_loads:
        link = links.get(load["link_id"])
        vehicle_type = vehicle_types.get(load["vehicle"])
        if link is None or vehicle_type is None:
            continue
        distance = link["length"] * float(load["vehicle_count"])
        if distance <= 0:
            continue
        grade = link["grade"] if load["forward"] else -link["grade"]
        gradient_bin = _snap(grade, GRADIENT_BINS)
        payload_bin = _snap(float(load["load_pct"]) * 100, PAYLOAD_BINS)

        for pollutant in sorted(pollutants.get(vehicle_type, ())):
            coefficient = coefficients.get((vehicle_type, pollutant, gradient_bin, payload_bin))
            if coefficient is None:
                continue
            factor = _hot_emission_factor(coefficient, float(load["velocity"]))
            if factor is None:
                continue
            output.append({
                "link_id": load["link_id"], "time_interval": load["time_interval"],
                "resource": load["resource"], "vehicle": load["vehicle"], "forward": load["forward"],
                "pollutant": pollutant, "source": "exhaust", "grams": factor * distance,
            })
        for (candidate_type, pollutant), factor in sorted(non_exhaust.items()):
            if candidate_type == vehicle_type:
                output.append({
                    "link_id": load["link_id"], "time_interval": load["time_interval"],
                    "resource": load["resource"], "vehicle": load["vehicle"], "forward": load["forward"],
                    "pollutant": pollutant, "source": "non-exhaust", "grams": factor * distance,
                })
    return output
