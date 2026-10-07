"""Carrier-attributable delay metrics.

All functions take the output of ``data.analysis_frame``: completed flights with
a usable cause breakdown. "Carrier-attributable" means BTS ``CarrierDelay``:
causes within the airline's control (maintenance, crew, cleaning, fuelling,
baggage, ...). It is NOT a mechanical-delay measure.

Core metrics per group:

* ``carrier_min_per_flight`` - carrier-attributable delay minutes per completed
  flight (headline metric; combines how often and how long).
* ``carrier_delayed_rate`` - share of flights with any carrier-attributable
  delay minutes (only assigned when arrival delay >= 15 min).
* ``carrier_share`` - carrier minutes as a share of all cause-coded minutes.
* ``index`` - ``carrier_min_per_flight`` relative to the network (1.0 = average).
* ``excess_hours`` - carrier-delay hours above what the network rate would give
  for the same number of flights. This is the "number attached" to a finding.
"""

from __future__ import annotations

import pandas as pd

CAUSES = ["carrier_delay", "weather_delay", "nas_delay", "security_delay", "late_aircraft_delay"]
CAUSE_LABELS = {
    "carrier_delay": "Carrier",
    "weather_delay": "Weather",
    "nas_delay": "NAS (air traffic system)",
    "security_delay": "Security",
    "late_aircraft_delay": "Late-arriving aircraft",
}


def network_summary(af: pd.DataFrame) -> pd.Series:
    total_cause = af[CAUSES].sum().sum()
    return pd.Series(
        {
            "flights": len(af),
            "carrier_min_per_flight": af["carrier_delay"].mean(),
            "carrier_delayed_rate": (af["carrier_delay"] > 0).mean(),
            "carrier_share": af["carrier_delay"].sum() / total_cause,
            "on_time_rate": 1 - af["arr_del15"].mean(),
        }
    )


def cause_breakdown(af: pd.DataFrame) -> pd.DataFrame:
    """Total minutes and share of cause-coded delay, network-wide."""
    minutes = af[CAUSES].sum()
    return pd.DataFrame(
        {"cause": [CAUSE_LABELS[c] for c in CAUSES], "minutes": minutes.values, "share": (minutes / minutes.sum()).values}
    ).sort_values("minutes", ascending=False, ignore_index=True)


def group_metrics(af: pd.DataFrame, by: str | list[str], min_flights: int = 0) -> pd.DataFrame:
    """Carrier-attributable delay metrics per group, compared against the network."""
    net = network_summary(af)
    g = af.assign(_carrier_delayed=af["carrier_delay"] > 0, _cause_total=af[CAUSES].sum(axis=1)).groupby(
        by, observed=True
    )
    out = pd.DataFrame(
        {
            "flights": g.size(),
            "carrier_min_per_flight": g["carrier_delay"].mean(),
            "carrier_delayed_rate": g["_carrier_delayed"].mean(),
            "carrier_share": g["carrier_delay"].sum() / g["_cause_total"].sum(),
            "on_time_rate": 1 - g["arr_del15"].mean(),
        }
    )
    out["index"] = out["carrier_min_per_flight"] / net["carrier_min_per_flight"]
    out["excess_hours"] = (out["carrier_min_per_flight"] - net["carrier_min_per_flight"]) * out["flights"] / 60
    out = out[out["flights"] >= min_flights]
    return out.sort_values("carrier_min_per_flight", ascending=False)


def yearly_index(af: pd.DataFrame, by: str, min_flights: int = 0) -> pd.DataFrame:
    """``index`` computed separately per calendar year (one column per year), each
    year against that year's own network rate. A finding should hold in every year."""
    years = sorted(af["date"].dt.year.unique())
    cols = {
        y: group_metrics(af[af["date"].dt.year == y], by, min_flights=min_flights)["index"] for y in years
    }
    return pd.DataFrame(cols).add_prefix("index_")


TIME_BANDS = {"<09:00": (0, 9), "09–13": (9, 13), "13–17": (13, 17), "17–21": (17, 21), "21+": (21, 24)}


def time_band(af: pd.DataFrame) -> pd.Series:
    """Scheduled-departure time band, as an ordered categorical."""
    edges = [lo for lo, _ in TIME_BANDS.values()] + [24]
    return pd.cut(af["dep_hour"].astype(int), edges, right=False, labels=list(TIME_BANDS))


def excess_by_band(af: pd.DataFrame, carrier: str) -> pd.DataFrame:
    """One carrier vs the network within each time band: rate, gap and excess hours per year."""
    years = af["date"].dt.year.nunique()
    af = af.assign(band=time_band(af))
    network = af.groupby("band", observed=True)["carrier_delay"].mean()
    g = af[af["carrier"] == carrier].groupby("band", observed=True)["carrier_delay"]
    out = pd.DataFrame({"flights": g.size(), "min_per_flight": g.mean(), "network_min_per_flight": network})
    out["vs_network"] = out["min_per_flight"] / out["network_min_per_flight"]
    out["excess_hours_per_year"] = (out["min_per_flight"] - out["network_min_per_flight"]) * out["flights"] / 60 / years
    out["share_of_flights"] = out["flights"] / out["flights"].sum()
    out["share_of_excess"] = out["excess_hours_per_year"] / out["excess_hours_per_year"].sum()
    return out


def mix_adjusted(af: pd.DataFrame, entity: str, control: str, min_flights: int = 0) -> pd.DataFrame:
    """Actual vs expected carrier-delay minutes, controlling for ``control``.

    E.g. ``entity="carrier", control="origin"`` asks whether a carrier is worse
    than other carriers *at the same airports*, rather than just flying from
    harder airports. ``expected`` uses each flight's ``control``-group average.
    ``adj_index`` > 1 means worse than expected given its mix.
    """
    expected = af.groupby(control, observed=True)["carrier_delay"].transform("mean")
    g = af.assign(_expected=expected).groupby(entity, observed=True)
    out = pd.DataFrame(
        {
            "flights": g.size(),
            "actual_min_per_flight": g["carrier_delay"].mean(),
            "expected_min_per_flight": g["_expected"].mean(),
        }
    )
    out["adj_index"] = out["actual_min_per_flight"] / out["expected_min_per_flight"]
    out = out[out["flights"] >= min_flights]
    return out.sort_values("adj_index", ascending=False)


def grid(af: pd.DataFrame, rows: str, cols: str, value: str = "carrier_delay", min_flights: int = 0) -> pd.DataFrame:
    """Mean ``value`` per (rows, cols) cell; cells under ``min_flights`` become NaN."""
    g = af.groupby([rows, cols], observed=True)[value]
    mean = g.mean().unstack(cols)
    n = g.size().unstack(cols)
    return mean.where(n >= min_flights)
