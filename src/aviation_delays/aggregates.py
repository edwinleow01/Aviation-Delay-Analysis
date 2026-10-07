"""Small pre-aggregated tables for the Streamlit app.

The cleaned flight file is ~85 MB (14M rows), too big to ship with a web app.
Every number the app shows can be rebuilt from two sums-and-counts tables, a few
thousand rows each, which are committed under ``app/aggregates/``:

* ``by_airport``: carrier x origin x year (cause-minute sums, for the airport views
  and the airport-mix control)
* ``by_time``: carrier x scheduled departure hour x weekday x year

The functions below reproduce the notebook metrics from those tables;
``tests/test_aggregates.py`` checks that they match.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .metrics import CAUSES, TIME_BANDS

AGG_DIR = Path(__file__).resolve().parents[2] / "app" / "aggregates"
FLAG_INDEX = 1.2


def _sums(af: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    df = af.assign(year=af["date"].dt.year, carrier_delayed=af["carrier_delay"] > 0)
    g = df.groupby(keys, observed=True)
    out = g[CAUSES].sum().astype("float64")
    out.insert(0, "flights", g.size())
    out["carrier_delayed"] = g["carrier_delayed"].sum()
    out["arr_del15"] = g["arr_del15"].sum()
    return out.reset_index()


def build(af: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """From ``data.analysis_frame`` output to the two app tables."""
    by_airport = _sums(af, ["carrier", "origin", "year"])
    by_time = _sums(af, ["carrier", "dep_hour", "day_of_week", "year"])
    for t in (by_airport, by_time):
        t["carrier"] = t["carrier"].astype(str)
    by_airport["origin"] = by_airport["origin"].astype(str)
    by_time[["dep_hour", "day_of_week"]] = by_time[["dep_hour", "day_of_week"]].astype(int)
    return {"by_airport": by_airport, "by_time": by_time}


def save(tables: dict[str, pd.DataFrame], out_dir: Path = AGG_DIR) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, t in tables.items():
        t.to_csv(out_dir / f"{name}.csv", index=False, float_format="%.1f")


def load(agg_dir: Path = AGG_DIR) -> dict[str, pd.DataFrame]:
    return {
        "by_airport": pd.read_csv(agg_dir / "by_airport.csv", dtype={"carrier": str, "origin": str}),
        "by_time": pd.read_csv(agg_dir / "by_time.csv", dtype={"carrier": str}),
    }


# ---- metrics from the aggregates -------------------------------------------------


def network_rate(t: pd.DataFrame) -> float:
    return t["carrier_delay"].sum() / t["flights"].sum()


def _rate(t: pd.DataFrame, by: list[str]) -> pd.DataFrame:
    g = t.groupby(by)[["flights", "carrier_delay", "carrier_delayed"]].sum()
    g["min_per_flight"] = g["carrier_delay"] / g["flights"]
    g["delayed_rate"] = g["carrier_delayed"] / g["flights"]
    return g


def entity_table(by_airport: pd.DataFrame, entity: str, min_flights: int = 0) -> pd.DataFrame:
    """Per carrier (``entity="carrier"``) or per airport (``"origin"``): rate, index vs
    network, mix-adjusted index, index per year, excess hours a year, flag."""
    control = "origin" if entity == "carrier" else "carrier"
    years = sorted(by_airport["year"].unique())
    out = _rate(by_airport, [entity])
    out["index"] = out["min_per_flight"] / network_rate(by_airport)
    out["excess_hours_per_year"] = (
        (out["min_per_flight"] - network_rate(by_airport)) * out["flights"] / 60 / len(years)
    )

    # Mix control: expected minutes if each flight had its control group's average rate.
    control_rate = _rate(by_airport, [control])["min_per_flight"]
    cells = by_airport.groupby([entity, control])["flights"].sum().reset_index()
    cells["expected"] = cells["flights"] * cells[control].map(control_rate)
    expected = cells.groupby(entity)["expected"].sum()
    out["adj_index"] = out["carrier_delay"] / expected

    for y in years:
        ty = by_airport[by_airport["year"] == y]
        out[f"index_{y}"] = _rate(ty, [entity])["min_per_flight"] / network_rate(ty)
    year_cols = [f"index_{y}" for y in years]
    out = out[out["flights"] >= min_flights]
    out["flagged"] = (
        (out["index"] >= FLAG_INDEX) & (out["adj_index"] >= FLAG_INDEX) & (out[year_cols] >= FLAG_INDEX).all(axis=1)
    )
    return out.drop(columns=["carrier_delay", "carrier_delayed"]).sort_values("min_per_flight", ascending=False)


def hour_profile(by_time: pd.DataFrame, carrier: str | None = None) -> pd.Series:
    t = by_time if carrier is None else by_time[by_time["carrier"] == carrier]
    return _rate(t, ["dep_hour"])["min_per_flight"]


def weekday_profile(by_time: pd.DataFrame, carrier: str | None = None) -> pd.Series:
    t = by_time if carrier is None else by_time[by_time["carrier"] == carrier]
    return _rate(t, ["day_of_week"])["min_per_flight"]


def _band(hours: pd.Series) -> pd.Series:
    edges = [lo for lo, _ in TIME_BANDS.values()] + [24]
    return pd.cut(hours, edges, right=False, labels=list(TIME_BANDS))


def band_table(by_time: pd.DataFrame, carrier: str) -> pd.DataFrame:
    """One carrier vs the network in each time band (same as ``metrics.excess_by_band``)."""
    years = by_time["year"].nunique()
    t = by_time.assign(band=_band(by_time["dep_hour"]))
    network = _rate(t, ["band"])["min_per_flight"]
    out = _rate(t[t["carrier"] == carrier], ["band"])[["flights", "min_per_flight"]]
    out["network_min_per_flight"] = network
    out["vs_network"] = out["min_per_flight"] / out["network_min_per_flight"]
    out["excess_hours_per_year"] = (out["min_per_flight"] - out["network_min_per_flight"]) * out["flights"] / 60 / years
    return out


def what_if(by_time: pd.DataFrame, carrier: str, bands: list[str], close_gap: float = 1.0) -> float:
    """Delay hours a year removed if ``carrier`` closed ``close_gap`` (0-1) of its gap to the
    network rate in the chosen time bands. Bands where it already beats the network count as 0."""
    b = band_table(by_time, carrier).loc[bands, "excess_hours_per_year"]
    return float(b.clip(lower=0).sum() * close_gap)
