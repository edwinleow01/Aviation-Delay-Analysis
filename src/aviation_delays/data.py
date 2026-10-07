"""Load and clean BTS On-Time Performance data.

The analysis only needs a dozen of the ~110 BTS columns. Raw monthly files are
read with just those columns, normalised to one naming scheme (the transtats
PREZIP names, e.g. ``Reporting_Airline``), cleaned, and stored as a single
Parquet file in ``data/processed/``.

Cleaning rules (see README "Data notes" for the reasoning):

* Cancelled and diverted flights have no arrival delay or cause breakdown.
  They are kept but flagged via ``status``; delay metrics use completed flights.
* BTS only fills the five cause fields when a flight arrives >= 15 min late
  (``ArrDel15 == 1``). For on-time/slightly-late completed flights the cause
  fields are NaN, which here means 0 minutes, not "unknown".
* A completed, >= 15 min late flight with NaN causes is genuinely missing and
  is flagged with ``cause_missing`` so it can be counted and excluded.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = PROJECT_ROOT / "data" / "raw"
PROCESSED_PATH = PROJECT_ROOT / "data" / "processed" / "flights.parquet"

CAUSE_COLUMNS = [
    "CarrierDelay",
    "WeatherDelay",
    "NASDelay",
    "SecurityDelay",
    "LateAircraftDelay",
]

COLUMNS = [
    "FlightDate",
    "Reporting_Airline",
    "Origin",
    "Dest",
    "CRSDepTime",
    "DepDelay",
    "ArrDelay",
    "ArrDel15",
    "Cancelled",
    "Diverted",
    *CAUSE_COLUMNS,
]

# Column names used by the BTS "Download" page and most Kaggle mirrors.
ALIASES = {
    "FL_DATE": "FlightDate",
    "OP_UNIQUE_CARRIER": "Reporting_Airline",
    "OP_CARRIER": "Reporting_Airline",
    "ORIGIN": "Origin",
    "DEST": "Dest",
    "CRS_DEP_TIME": "CRSDepTime",
    "DEP_DELAY": "DepDelay",
    "ARR_DELAY": "ArrDelay",
    "ARR_DEL15": "ArrDel15",
    "CANCELLED": "Cancelled",
    "DIVERTED": "Diverted",
    "CARRIER_DELAY": "CarrierDelay",
    "WEATHER_DELAY": "WeatherDelay",
    "NAS_DELAY": "NASDelay",
    "SECURITY_DELAY": "SecurityDelay",
    "LATE_AIRCRAFT_DELAY": "LateAircraftDelay",
}

DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def read_raw(path: str | Path) -> pd.DataFrame:
    """Read one raw BTS file (CSV, zipped CSV or Parquet) with only the needed columns."""
    path = Path(path)
    wanted = set(COLUMNS) | set(ALIASES)
    if path.suffix == ".parquet":
        df = pd.read_parquet(path)
        df = df[[c for c in df.columns if c in wanted]]
    else:
        df = pd.read_csv(path, usecols=lambda c: c in wanted, low_memory=False)
    df = df.rename(columns=ALIASES)
    missing = [c for c in COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"{path.name} is missing required columns: {missing}")
    return df[COLUMNS]


def clean(df: pd.DataFrame) -> pd.DataFrame:
    """Return an analysis-ready frame. Does not drop rows; flags them instead."""
    out = pd.DataFrame(
        {
            "date": pd.to_datetime(df["FlightDate"]).dt.normalize(),
            "carrier": df["Reporting_Airline"].astype("string").str.strip(),
            "origin": df["Origin"].astype("string").str.strip(),
            "dest": df["Dest"].astype("string").str.strip(),
        }
    )

    # CRSDepTime is local scheduled time as hhmm (e.g. 5, 930, 2359; 2400 = midnight).
    hhmm = pd.to_numeric(df["CRSDepTime"], errors="coerce")
    out["dep_hour"] = ((hhmm // 100) % 24).astype("Int8")
    out["day_of_week"] = out["date"].dt.dayofweek.astype("Int8")  # Mon=0

    cancelled = df["Cancelled"].fillna(0).astype(float) == 1
    diverted = df["Diverted"].fillna(0).astype(float) == 1
    out["status"] = pd.Categorical(
        np.select([cancelled, diverted], ["cancelled", "diverted"], default="completed"),
        categories=["completed", "cancelled", "diverted"],
    )
    completed = out["status"] == "completed"

    out["dep_delay"] = pd.to_numeric(df["DepDelay"], errors="coerce")
    out["arr_delay"] = pd.to_numeric(df["ArrDelay"], errors="coerce")
    arr_del15 = pd.to_numeric(df["ArrDel15"], errors="coerce")
    # Recompute where ArrDel15 is absent but ArrDelay is present.
    arr_del15 = arr_del15.fillna((out["arr_delay"] >= 15).astype(float).where(out["arr_delay"].notna()))
    out["arr_del15"] = (arr_del15 == 1) & completed

    causes = df[CAUSE_COLUMNS].apply(pd.to_numeric, errors="coerce")
    no_causes = causes.isna().all(axis=1)
    out["cause_missing"] = out["arr_del15"] & no_causes
    # Not delayed >= 15 min -> no cause minutes were assigned: that is 0, not unknown.
    on_time = completed & ~out["arr_del15"]
    causes = causes.where(~on_time, causes.fillna(0))
    # Partially filled rows (some causes NaN, some not): treat the NaNs as 0.
    causes = causes.where(no_causes, causes.fillna(0))
    # Non-completed flights carry no cause minutes.
    causes = causes.where(completed)
    snake = {
        "CarrierDelay": "carrier_delay",
        "WeatherDelay": "weather_delay",
        "NASDelay": "nas_delay",
        "SecurityDelay": "security_delay",
        "LateAircraftDelay": "late_aircraft_delay",
    }
    for src, dst in snake.items():
        out[dst] = causes[src].astype("float32")

    for col in ("carrier", "origin", "dest"):
        out[col] = out[col].astype("category")
    return out


def cleaning_summary(flights: pd.DataFrame) -> pd.Series:
    """Counts worth reporting in the writeup's method section."""
    completed = flights["status"] == "completed"
    return pd.Series(
        {
            "rows": len(flights),
            "date_min": flights["date"].min().date(),
            "date_max": flights["date"].max().date(),
            "carriers": flights["carrier"].nunique(),
            "origin_airports": flights["origin"].nunique(),
            "completed": int(completed.sum()),
            "cancelled": int((flights["status"] == "cancelled").sum()),
            "diverted": int((flights["status"] == "diverted").sum()),
            "arr_delayed_15": int(flights["arr_del15"].sum()),
            "delayed_cause_missing": int(flights["cause_missing"].sum()),
            "missing_dep_hour": int(flights["dep_hour"].isna().sum()),
        }
    )


def analysis_frame(flights: pd.DataFrame) -> pd.DataFrame:
    """Completed flights with a usable cause breakdown: the denominator for delay metrics."""
    mask = (flights["status"] == "completed") & ~flights["cause_missing"] & flights["dep_hour"].notna()
    return flights[mask]


def build_processed(raw_dir: str | Path = RAW_DIR, out_path: str | Path = PROCESSED_PATH) -> pd.DataFrame:
    """Clean every raw file in ``raw_dir`` and write one Parquet file."""
    raw_dir, out_path = Path(raw_dir), Path(out_path)
    files = sorted(
        p for p in raw_dir.iterdir() if p.suffix in {".csv", ".parquet", ".zip"} or p.name.endswith(".csv.gz")
    )
    if not files:
        raise FileNotFoundError(f"No raw files in {raw_dir}. Run scripts/download_bts.py first (see README).")
    flights = pd.concat([clean(read_raw(p)) for p in files], ignore_index=True)
    for col in ("carrier", "origin", "dest"):
        flights[col] = flights[col].astype("category")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    flights.to_parquet(out_path, index=False)
    return flights


def load_processed(path: str | Path = PROCESSED_PATH) -> pd.DataFrame:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"{path} not found. Run `python scripts/build_dataset.py` first (see README).")
    return pd.read_parquet(path)
