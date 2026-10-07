"""Download BTS On-Time Performance monthly files into data/raw/.

Each monthly zip from transtats (~25-30 MB, ~110 columns) is reduced to the
columns this analysis needs and saved as data/raw/<year>_<month>.parquet.

    python scripts/download_bts.py                      # 2024-01 .. 2025-12
    python scripts/download_bts.py --start 2025-01 --end 2025-12

If transtats blocks scripted downloads, use the manual route in the README and
drop the CSVs into data/raw/ instead; build_dataset.py reads those too.
"""

from __future__ import annotations

import argparse
import io
import sys
import time
import zipfile
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from aviation_delays.data import ALIASES, COLUMNS, RAW_DIR  # noqa: E402

URL = "https://transtats.bts.gov/PREZIP/On_Time_Reporting_Carrier_On_Time_Performance_1987_present_{year}_{month}.zip"


def months(start: str, end: str):
    for p in pd.period_range(start, end, freq="M"):
        yield p.year, p.month


def fetch(year: int, month: int, retries: int = 4) -> bytes:
    url = URL.format(year=year, month=month)
    for attempt in range(retries):
        try:
            r = requests.get(url, timeout=300)
            r.raise_for_status()
            return r.content
        except requests.RequestException as e:
            if attempt == retries - 1:
                raise
            wait = 2 ** (attempt + 1)
            print(f"  {e} - retrying in {wait}s")
            time.sleep(wait)
    raise AssertionError("unreachable")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start", default="2024-01", help="first month, YYYY-MM")
    ap.add_argument("--end", default="2025-12", help="last month, YYYY-MM")
    ap.add_argument("--out", type=Path, default=RAW_DIR)
    ap.add_argument("--force", action="store_true", help="re-download months already present")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    wanted = set(COLUMNS) | set(ALIASES)
    failed = []
    for year, month in months(args.start, args.end):
        dest = args.out / f"{year}_{month:02d}.parquet"
        if dest.exists() and not args.force:
            print(f"{year}-{month:02d}: already downloaded")
            continue
        print(f"{year}-{month:02d}: downloading")
        try:
            blob = fetch(year, month)
        except requests.RequestException as e:
            print(f"  failed: {e}")
            failed.append(f"{year}-{month:02d}")
            continue
        with zipfile.ZipFile(io.BytesIO(blob)) as zf:
            csv_name = next(n for n in zf.namelist() if n.lower().endswith(".csv"))
            with zf.open(csv_name) as f:
                df = pd.read_csv(f, usecols=lambda c: c in wanted, low_memory=False)
        df.to_parquet(dest, index=False)
        print(f"  saved {len(df):,} rows -> {dest.relative_to(args.out.parent.parent)}")

    if failed:
        print(f"\nFailed months: {', '.join(failed)} (BTS may not have published them yet).")
        sys.exit(1)


if __name__ == "__main__":
    main()
