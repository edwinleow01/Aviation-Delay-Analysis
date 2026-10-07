"""Write the small aggregate tables the Streamlit app reads (app/aggregates/*.csv)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from aviation_delays import aggregates, data  # noqa: E402


def main() -> None:
    af = data.analysis_frame(data.load_processed())
    tables = aggregates.build(af)
    aggregates.save(tables)
    for name, t in tables.items():
        print(f"{name}: {len(t):,} rows -> {aggregates.AGG_DIR / (name + '.csv')}")


if __name__ == "__main__":
    main()
