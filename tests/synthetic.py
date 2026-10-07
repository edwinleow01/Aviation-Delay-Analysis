"""Synthetic BTS-shaped data for tests and notebook smoke runs.

NOT real data - never use it for findings. It exists so the pipeline and
notebooks can be exercised without the multi-GB BTS download.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def make_raw(n: int = 20_000, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    carriers = np.array(["AA", "DL", "UA", "WN", "B6", "NK"])
    airports = np.array(["ATL", "DFW", "DEN", "ORD", "LAX", "JFK", "CLT", "LAS"])
    dates = pd.Timestamp("2024-01-01") + pd.to_timedelta(rng.integers(0, 366, n), unit="D")
    hour = rng.integers(5, 24, n)
    crs = hour * 100 + rng.integers(0, 60, n)
    carrier = rng.choice(carriers, n)
    origin = rng.choice(airports, n)
    dest = rng.choice(airports, n)

    cancelled = rng.random(n) < 0.02
    diverted = ~cancelled & (rng.random(n) < 0.003)
    completed = ~cancelled & ~diverted

    base = rng.gamma(1.2, 9, n) - 8
    base += np.where(carrier == "NK", 6, 0) + (hour - 5) * 0.4
    arr = np.where(completed, np.round(base), np.nan)
    del15 = np.where(completed, (arr >= 15).astype(float), np.nan)

    late = completed & (arr >= 15)
    share = rng.dirichlet([2, 0.4, 1.5, 0.05, 2], n)
    causes = np.where(late[:, None], np.round(share * np.nan_to_num(arr)[:, None]), np.nan)
    # a handful of delayed flights with missing cause data
    causes[late & (rng.random(n) < 0.01)] = np.nan

    return pd.DataFrame(
        {
            "FlightDate": dates.strftime("%Y-%m-%d"),
            "Reporting_Airline": carrier,
            "Origin": origin,
            "Dest": dest,
            "CRSDepTime": crs,
            "DepDelay": np.where(cancelled, np.nan, np.round(base - 3)),
            "ArrDelay": arr,
            "ArrDel15": del15,
            "Cancelled": cancelled.astype(float),
            "Diverted": diverted.astype(float),
            "CarrierDelay": causes[:, 0],
            "WeatherDelay": causes[:, 1],
            "NASDelay": causes[:, 2],
            "SecurityDelay": causes[:, 3],
            "LateAircraftDelay": causes[:, 4],
            "ExtraColumnIgnored": 1,
        }
    )
