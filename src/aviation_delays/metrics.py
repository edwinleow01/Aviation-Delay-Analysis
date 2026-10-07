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

import numpy as np
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
    # z-score of the carrier-delayed rate vs network (binomial). With millions of
    # flights nearly everything is "significant"; use it to screen out small-n noise.
    p = net["carrier_delayed_rate"]
    out["rate_z"] = (out["carrier_delayed_rate"] - p) / np.sqrt(p * (1 - p) / out["flights"])
    out = out[out["flights"] >= min_flights]
    return out.sort_values("carrier_min_per_flight", ascending=False)


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
