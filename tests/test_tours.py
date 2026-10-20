import geopandas
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import LineString, Point, box

from netsy.helpers import validate
from netsy.synth.tours import tours
from tests.fixtures import CRS

# Zones 1 to 4 on a line, 10 km apart, an hour apart.
ZONES = ["1", "2", "3", "4"]
STEPS = np.abs(np.subtract.outer(np.arange(4), np.arange(4))).astype(np.float32)


def _zones():
    return geopandas.GeoDataFrame(
        {"zone_id": [1, 2, 3, 4], "region": ["in"] * 4, "urban": [1, 0, 0, 0]},
        geometry=[box(i, 0, i + 1, 1) for i in range(4)], crs=CRS,
    )


def _facilities():
    return geopandas.GeoDataFrame(
        {"facility_id": ["dc"], "facility_type": ["distribution_centre"], "zone_id": [1]},
        geometry=[Point(0.5, 0.5)], crs=CRS,
    )


def _shipments(rows):
    """Rows of (origin zone, destination zone, quantity, vehicle, segment,
    window start, window end, origin facility).
    """
    table = pd.DataFrame(rows, columns=[
        "origin_zone_id", "destination_zone_id", "quantity", "vehicle", "segment", "window_start", "window_end", "origin_facility_id",
    ])
    table.insert(0, "transaction_id", range(1, len(table) + 1))
    table.insert(1, "resource", "grain")
    table["origin_agent_id"] = pd.array([None if f else 1 for f in table["origin_facility_id"]], dtype="Int64")
    table["destination_agent_id"] = pd.array([2] * len(table), dtype="Int64")
    table["window"] = table["window_start"].astype(str)
    lines = [LineString([(o, 0), (d, 0)]) for o, d in zip(table["origin_zone_id"], table["destination_zone_id"])]
    return geopandas.GeoDataFrame(table, geometry=lines, crs=CRS)


def _table(rows, columns, check):
    return check(pd.DataFrame(rows, columns=columns).astype(str).replace({"nan": np.nan, "None": np.nan}))


def _settings(**changes):
    rows = {"independent_carriers": 1, "mean_dwell_time": 0, **changes}
    pairs = []
    for name, value in rows.items():
        pairs.extend((name, v) for v in (value if isinstance(value, list) else [value]))
    return _table(pairs, ["setting", "value"], validate.check_tour_settings)


def _end(rows):
    return _table(rows, ["term", "value"], validate.check_end_tour)


# Tours that never end by choice, and tours that always do.
GO_ON = [("constant", -50)]
STOP = [("constant", 50)]
DAY = (8, 18)


def _synth(rows, seed=0, settings=None, first=GO_ON, later=GO_ON, facilities=True, vehicles=None):
    vehicles = vehicles or [("van", 4.0, 1, 1), ("truck", 20.0, 1, 1)]
    return tours(
        _zones(), _facilities() if facilities else None, (list(ZONES), STEPS.copy(), STEPS * 10),
        _shipments(rows),
        _table(vehicles, ["vehicle", "capacity", "cost_per_hour", "cost_per_km"], validate.check_shipment_vehicles),
        settings if settings is not None else _settings(), _end(first), _end(later), rng=np.random.default_rng(seed),
    )


def test_trip_columns_and_closed_tours():
    trips, parts = _synth([(1, 2, 1.0, "van", "a", *DAY, None), (1, 3, 1.0, "van", "a", *DAY, None)])
    assert list(trips.columns) == [
        "tour_id", "trip", "carrier", "vehicle", "resource", "segment", "shipments", "tour_quantity", "quantity",
        "utilization", "tour_departure", "departure", "arrival", "origin_zone_id", "destination_zone_id", "geometry",
    ]
    for _, tour in trips.groupby("tour_id"):
        assert tour["trip"].tolist() == list(range(1, len(tour) + 1))
        assert tour["origin_zone_id"].iloc[0] == tour["destination_zone_id"].iloc[-1]
        assert (tour["origin_zone_id"].iloc[1:].to_numpy() == tour["destination_zone_id"].iloc[:-1].to_numpy()).all()
    assert list(parts.columns) == ["transaction_id", "tour_id", "quantity"]


def test_one_tour_loads_then_unloads_nearest_first_and_returns_empty():
    trips, _ = _synth([(1, 3, 1.0, "van", "a", *DAY, None), (1, 2, 1.0, "van", "a", *DAY, None)])
    assert trips["tour_id"].nunique() == 1
    assert list(zip(trips["origin_zone_id"], trips["destination_zone_id"])) == [(1, 2), (2, 3), (3, 1)]
    assert trips["quantity"].tolist() == [2.0, 1.0, 0.0]
    assert trips["resource"].isna().tolist() == [False, False, True]


def test_a_shipment_heavier_than_its_vehicle_is_split_into_equal_parts():
    _, parts = _synth([(1, 2, 10.0, "van", "a", *DAY, None)], first=STOP)
    assert parts["quantity"].tolist() == [10 / 3] * 3
    assert parts["tour_id"].nunique() == 3


def test_tours_end_by_choice():
    rows = [(1, 2, 1.0, "van", "a", *DAY, None)] * 4
    assert _synth(rows, first=STOP)[1]["tour_id"].nunique() == 4
    assert _synth(rows)[1]["tour_id"].nunique() == 1


def test_a_tour_takes_at_most_max_shipments_after_its_first():
    rows = [(1, 2, 0.1, "van", "a", *DAY, None)] * 7
    _, parts = _synth(rows, settings=_settings(max_shipments=2))
    assert parts.groupby("tour_id").size().tolist() == [3, 3, 1]


def test_a_tour_fills_its_vehicle_up_to_the_slack():
    rows = [(1, 2, 1.5, "van", "a", *DAY, None)] * 4
    trips, _ = _synth(rows, settings=_settings(capacity_slack=1.2))
    assert (trips.groupby("tour_id")["tour_quantity"].first() <= 1.2 * 4.0).all()
    assert trips["tour_id"].nunique() == 2


def test_tours_keep_their_same_strata_together():
    rows = [(1, 2, 1.0, "van", "a", *DAY, None), (1, 2, 1.0, "van", "b", *DAY, None)] * 2
    trips, _ = _synth(rows, settings=_settings(same_stratum="segment"))
    assert (trips.groupby("tour_id")["segment"].nunique() == 1).all()
    assert trips["tour_id"].nunique() == 2


def test_tours_mix_only_neighbouring_windows():
    windows = [(0, 8), (8, 12), (12, 18), (18, 24)]
    rows = [(1, 2, 0.1, "van", "a", *window, None) for window in windows for _ in range(3)]
    trips, parts = _synth(rows)
    starts = parts.merge(pd.DataFrame({"transaction_id": range(1, len(rows) + 1), "start": [r[5] for r in rows]}))
    for _, tour in starts.groupby("tour_id"):
        index = sorted({[w[0] for w in windows].index(s) for s in tour["start"]})
        assert len(index) <= 2 and (len(index) < 2 or index[1] - index[0] in (1, 3))


def test_parts_at_a_carrier_facility_are_carried_from_it():
    rows = [(1, 3, 1.0, "van", "a", *DAY, "dc"), (2, 4, 1.0, "van", "a", *DAY, None)]
    trips, _ = _synth(rows, settings=_settings(carrier_facility_type="distribution_centre"), first=STOP)
    carriers = trips.groupby("tour_id")["carrier"].first().tolist()
    assert sorted(carriers) == ["dc", "independent_1"]


def test_a_based_carrier_starts_from_its_base():
    rows = [(2, 3, 1.0, "van", "a", *DAY, "dc"), (2, 4, 1.0, "van", "a", *DAY, "dc")]
    trips, _ = _synth(rows, settings=_settings(carrier_facility_type="distribution_centre"))
    assert trips["origin_zone_id"].iloc[0] == 1 == trips["destination_zone_id"].iloc[-1]


def test_departure_centres_the_window_on_the_next_arrival_as_mass_gt_does():
    # One shipment from zone 1 to zone 3, two hours each way, window 8-10:
    # MASS-GT compares the window of the stop at zone 3 with the arrival back
    # at zone 1, four hours after departure, so the tour leaves at 9 - 4.
    trips, _ = _synth([(1, 3, 1.0, "van", "a", 8, 10, None)], first=STOP)
    assert trips["tour_departure"].iloc[0] == pytest.approx(5.0)
    assert trips["departure"].tolist() == pytest.approx([5.0, 7.0])
    assert trips["arrival"].tolist() == pytest.approx([7.0, 9.0])


@pytest.mark.parametrize("term, value, ends", [
    ("zone:urban", 100, True), ("zone:urban", -100, False), ("vehicle:van", 100, True), ("vehicle:van", -100, False),
    ("origin:agent", 100, True), ("destination:agent", -100, False), ("resource:grain", 100, True),
])
def test_end_tour_terms_describe_the_first_shipment(term, value, ends):
    rows = [(1, 2, 1.0, "van", "a", *DAY, None)] * 3
    _, parts = _synth(rows, first=[("constant", 0), (term, value)], later=STOP)
    first_tour = parts.groupby("tour_id").size().iloc[0]
    assert (first_tour == 1) == ends


def test_an_unknown_term_or_setting_is_an_error():
    with pytest.raises(ValueError, match="end_tour_first.csv: unknown term 'speed'"):
        _synth([(1, 2, 1.0, "van", "a", *DAY, None)] * 2, first=[("speed", 1)])
    with pytest.raises(ValueError, match="tour_settings.csv: unknown setting 'colour'"):
        _synth([(1, 2, 1.0, "van", "a", *DAY, None)], settings=_settings(colour=1))


def test_a_vehicle_without_a_capacity_is_an_error():
    with pytest.raises(ValueError, match=r"vehicles \['bike'\] are not in shipment_vehicles.csv"):
        _synth([(1, 2, 1.0, "bike", "a", *DAY, None)])


def test_seed_repeats_the_same_tours():
    rows = [(o, d, 1.0, "van", "a", *DAY, None) for o in (1, 2) for d in (3, 4)] * 3
    a, b = _synth(rows, seed=4, first=[("constant", 0)], later=[("constant", 0)]), _synth(rows, seed=4, first=[("constant", 0)], later=[("constant", 0)])
    pd.testing.assert_frame_equal(pd.DataFrame(a[0].drop(columns="geometry")), pd.DataFrame(b[0].drop(columns="geometry")))
