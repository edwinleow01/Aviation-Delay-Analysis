import numpy as np
import pandas as pd
import pytest

from aviation_delays import data, metrics
from synthetic import make_raw


def raw_rows(**overrides):
    row = {
        "FlightDate": "2024-03-04",  # a Monday
        "Reporting_Airline": "AA",
        "Origin": "DFW",
        "Dest": "ORD",
        "CRSDepTime": 930,
        "DepDelay": 0.0,
        "ArrDelay": 0.0,
        "ArrDel15": 0.0,
        "Cancelled": 0.0,
        "Diverted": 0.0,
        **{c: np.nan for c in data.CAUSE_COLUMNS},
    }
    row.update(overrides)
    return row


def test_on_time_flight_gets_zero_cause_minutes():
    out = data.clean(pd.DataFrame([raw_rows()]))
    assert out.loc[0, "carrier_delay"] == 0
    assert not out.loc[0, "cause_missing"]
    assert out.loc[0, "dep_hour"] == 9
    assert out.loc[0, "day_of_week"] == 0


def test_delayed_flight_with_no_causes_is_flagged_missing():
    out = data.clean(pd.DataFrame([raw_rows(ArrDelay=40.0, ArrDel15=1.0)]))
    assert out.loc[0, "cause_missing"]
    assert pd.isna(out.loc[0, "carrier_delay"])
    assert len(data.analysis_frame(out)) == 0


def test_cancelled_and_diverted_excluded_from_analysis():
    df = pd.DataFrame(
        [
            raw_rows(Cancelled=1.0, ArrDelay=np.nan, ArrDel15=np.nan),
            raw_rows(Diverted=1.0, ArrDelay=np.nan, ArrDel15=np.nan),
            raw_rows(ArrDelay=30.0, ArrDel15=1.0, CarrierDelay=20.0, WeatherDelay=0.0, NASDelay=10.0,
                     SecurityDelay=0.0, LateAircraftDelay=0.0),
        ]
    )
    out = data.clean(df)
    assert list(out["status"]) == ["cancelled", "diverted", "completed"]
    af = data.analysis_frame(out)
    assert len(af) == 1 and af["carrier_delay"].iloc[0] == 20


def test_midnight_2400_maps_to_hour_0():
    out = data.clean(pd.DataFrame([raw_rows(CRSDepTime=2400)]))
    assert out.loc[0, "dep_hour"] == 0


def test_kaggle_style_columns_are_accepted(tmp_path):
    raw = make_raw(200)
    upper = {v: k for k, v in data.ALIASES.items() if k != "OP_CARRIER"}
    path = tmp_path / "kaggle.csv"
    raw.rename(columns=upper).to_csv(path, index=False)
    df = data.read_raw(path)
    assert list(df.columns) == data.COLUMNS


def test_build_and_metrics_on_synthetic(tmp_path):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    make_raw(5000, seed=1).to_csv(raw_dir / "2024_01.csv", index=False)
    flights = data.build_processed(raw_dir, tmp_path / "flights.parquet")
    summary = data.cleaning_summary(flights)
    assert summary["rows"] == 5000
    assert summary["delayed_cause_missing"] > 0

    af = data.analysis_frame(data.load_processed(tmp_path / "flights.parquet"))
    net = metrics.network_summary(af)
    by_carrier = metrics.group_metrics(af, "carrier")
    # flight-weighted mean of group rates equals the network rate
    weighted = (by_carrier["carrier_min_per_flight"] * by_carrier["flights"]).sum() / by_carrier["flights"].sum()
    assert weighted == pytest.approx(net["carrier_min_per_flight"])
    assert by_carrier["excess_hours"].sum() == pytest.approx(0, abs=1e-3)  # float32 storage
    # the synthetic "NK" is built to be worst
    assert by_carrier.index[0] == "NK"
    assert metrics.cause_breakdown(af)["share"].sum() == pytest.approx(1)
    adj = metrics.mix_adjusted(af, "carrier", "origin")
    assert set(adj.index) == set(by_carrier.index)


def test_excess_by_band_sums_to_carrier_total():
    af = data.analysis_frame(data.clean(make_raw(20_000, seed=2)))
    band = metrics.excess_by_band(af, "NK")
    assert band["share_of_flights"].sum() == pytest.approx(1)
    assert band["share_of_excess"].sum() == pytest.approx(1)
    yearly = metrics.yearly_index(af, "carrier")
    assert list(yearly.columns) == ["index_2024"]


def test_airport_labels():
    assert data.airport_label("DTW") == "Detroit, MI · DTW"
    assert data.airport_label("ZZZ") == "ZZZ"


def test_airport_coordinates_cover_every_airport():
    coords = data.airport_coords()
    assert coords[["lat", "lon"]].notna().all().all()
    assert coords.loc["DTW", "lat"] == pytest.approx(42.21, abs=0.01)
