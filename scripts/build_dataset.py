"""Clean everything in data/raw/ into data/processed/flights.parquet and print a summary."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from aviation_delays.data import PROCESSED_PATH, RAW_DIR, build_processed, cleaning_summary  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--raw", type=Path, default=RAW_DIR)
    ap.add_argument("--out", type=Path, default=PROCESSED_PATH)
    args = ap.parse_args()
    flights = build_processed(args.raw, args.out)
    print(cleaning_summary(flights).to_string())
    print(f"\nWrote {args.out}")


if __name__ == "__main__":
    main()
