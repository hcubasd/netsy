from shapely.geometry import LineString

from netsy.synth.network_emissions import _hot_emission_factor, _snap, network_emissions


def _coefficients(**overrides):
    coefficients = {
        "alpha": 0.0, "beta": 0.0, "gamma": 6.0, "delta": 0.0,
        "epsilon": 0.0, "zeta": 0.0, "eta": 2.0, "rf": 0.0,
    }
    coefficients.update(overrides)
    return coefficients


def _fixture():
    loads = [{
        "link_id": 0, "time_interval": "day", "resource": "parcels", "vehicle": "van",
        "forward": True, "vehicle_count": 1, "velocity": 10.0, "load_pct": 1.0,
    }]
    network = [{"link_id": 0, "grade": 4.0, "geometry": LineString([(0, 0), (2, 0)])}]
    vehicles = [{"vehicle": "van", "vehicle_type": "light"}]
    copert = [
        dict(vehicle_type="light", pollutant="nox", gradient_bin=gradient, payload_bin=payload, **_coefficients())
        for gradient in (-6, -4, -2, 0, 2, 4, 6)
        for payload in (0, 50, 100)
    ]
    factors = [{"vehicle_type": "light", "pollutant": "pm10", "emission_factor": 0.5}]
    return loads, network, vehicles, copert, factors


def test_snap_clamps_and_breaks_ties_downward():
    assert _snap(-99, (-6, -4, -2)) == -6
    assert _snap(99, (-6, -4, -2)) == -2
    assert _snap(1, (0, 2)) == 0


def test_hot_copert_factor_uses_speed_and_reduction_factor():
    assert _hot_emission_factor(_coefficients(), 10) == 3
    assert _hot_emission_factor(_coefficients(rf=0.25), 10) == 2.25
    assert _hot_emission_factor(_coefficients(), 0) is None
    assert _hot_emission_factor(_coefficients(gamma=-6), 10) == 0


def test_exhaust_scales_by_distance_and_vehicle_count():
    rows = network_emissions(*_fixture())
    exhaust = [row for row in rows if row["source"] == "exhaust"]
    assert exhaust == [{
        "link_id": 0, "time_interval": "day", "resource": "parcels", "vehicle": "van",
        "forward": True, "pollutant": "nox", "source": "exhaust", "grams": 6.0,
    }]


def test_non_exhaust_is_a_velocity_independent_g_per_kilometre_factor():
    fixture = list(_fixture())
    fixture[0] = [dict(fixture[0][0], velocity=0)]
    rows = network_emissions(*fixture)
    assert [row for row in rows if row["source"] == "exhaust"] == []
    non_exhaust = [row for row in rows if row["source"] == "non-exhaust"]
    assert non_exhaust[0]["grams"] == 1.0


def test_direction_flips_grade_and_payload_snaps_to_copert_grid():
    fixture = list(_fixture())
    fixture[3] = [
        dict(vehicle_type="light", pollutant="nox", gradient_bin=gradient, payload_bin=payload,
             **_coefficients(gamma=2 * gradient + payload / 10 + 20))
        for gradient in (-6, -4, -2, 0, 2, 4, 6)
        for payload in (0, 50, 100)
    ]
    forward = network_emissions(*fixture)
    fixture[0] = [dict(fixture[0][0], forward=False, load_pct=0.4)]
    backward = network_emissions(*fixture)
    forward_grams = [row["grams"] for row in forward if row["source"] == "exhaust"][0]
    backward_grams = [row["grams"] for row in backward if row["source"] == "exhaust"][0]
    assert forward_grams == 38.0
    assert backward_grams == 17.0
