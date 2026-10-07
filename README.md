# Aviation Delay Analysis

A data analytics case study that ends in a business recommendation, not a dashboard.

> **Research question (locked):** Which airports or carriers show disproportionately high
> carrier-attributable delay, and does time-of-day or day-of-week make it worse?

This analysis uses US DOT (BTS) flight data rather than Singapore data, since CAAS/data.gov.sg
only publishes aggregate monthly figures for Changi — no flight-level, cause-coded delay data is
publicly available. BTS was chosen as the best available public dataset with the granularity
needed for this kind of analysis.

## Result (BTS Jan 2024 – Dec 2025, 13.8M completed flights)

- **Carriers:** SkyWest (OO) and American (AA) run 1.54× and 1.38× the network's carrier-attributable
  delay per flight (8.0 and 7.2 min vs 5.2). Both stay ≥ 1.3× against other airlines at the same airports,
  in 2024 and 2025 separately, and with the July 2024 CrowdStrike outage removed.
- **Airports:** Detroit (DTW), Madison (MSN) and Des Moines (DSM) are flagged. The airport effect is much smaller
  than the carrier effect (about 5.6k vs 68k excess delay hours a year).
- **Time:** across the network, carrier-attributable delay is 2.0× higher at 22:00 than at 10:00. Sunday is
  the worst day and Wednesday the best. For both flagged carriers the gap is widest **before 09:00** (1.76× and 1.51× the network).
- **Recommendation:** SkyWest and American should fix first-wave (pre-09:00) departure readiness. Matching the network's
  pre-09:00 rate would remove about **20,600 carrier-attributable delay hours a year**.

Full report: [`report/aviation_delay_report.html`](report/aviation_delay_report.html) (charts in `report/figures/`).

## Quick start

```bash
make setup        # venv + dependencies (Python 3.10+)
make data         # download BTS 2024-01..2025-12 into data/raw/  (~25-30 MB per month zipped)
make dataset      # clean -> data/processed/flights.parquet, prints a cleaning summary
make test
```

Then open `notebooks/01_data_check.ipynb` (Week 1 gate) and `notebooks/02_analysis.ipynb` (Week 2).
`make report` runs the analysis and writes a code-free HTML report to
`report/aviation_delay_report.html`, plus chart PNGs in `report/figures/` for the portfolio page.

## Getting the source data

`data/` is git-ignored. Re-create it with one of these:

1. **Scripted (default):** `python scripts/download_bts.py --start 2024-01 --end 2025-12`
   fetches the monthly zips from `https://transtats.bts.gov/PREZIP/` and keeps only the needed columns.
2. **Manual (if transtats blocks scripts):** go to transtats.bts.gov → Aviation → *Airline On-Time
   Performance Data* → *Reporting Carrier On-Time Performance (1987–present)*, pick a year and month, tick
   the fields below and download. Unzip the CSVs into `data/raw/`.
3. **Kaggle mirror:** search "BTS airline delay" / "flight delay and cancellation dataset". Uppercase
   column names (`FL_DATE`, `OP_CARRIER`, `CARRIER_DELAY`, …) are mapped automatically. Drop the CSV in `data/raw/`.

Fields used: `FlightDate, Reporting_Airline, Origin, Dest, CRSDepTime, DepDelay, ArrDelay, ArrDel15,
Cancelled, Diverted, CarrierDelay, WeatherDelay, NASDelay, SecurityDelay, LateAircraftDelay`.

## Data notes and method

- **"Carrier-attributable," never "mechanical."** BTS has no mechanical-delay field. Maintenance is
  folded into `CarrierDelay` along with crew, cleaning, fuelling and baggage.
- **Cause fields only exist for flights ≥15 min late.** For completed flights under 15 min late, the NaN
  cause fields are set to 0 minutes. A ≥15-min-late flight with no causes is flagged `cause_missing`
  and excluded (and counted in the data check).
- **Cancelled / diverted** flights have no cause breakdown. They are flagged by `status` and left out of
  the delay metrics.
- **Time of day** = *scheduled* departure hour (`CRSDepTime`), so a late flight doesn't move into a later hour bucket.
- **Headline metric** = carrier-attributable delay minutes per completed flight. "Disproportionate" =
  ≥1.2× the network rate, and still ≥1.2× after controlling for mix (a carrier vs other carriers at
  the same airports, an airport vs the same carriers elsewhere). `excess_hours` turns the gap into
  the one number the recommendation carries.

## Layout

```
src/aviation_delays/   data.py (load/clean), metrics.py, charts.py
scripts/               download_bts.py, build_dataset.py
notebooks/             01_data_check.ipynb, 02_analysis.ipynb
report/                exported HTML report + figures (generated)
tests/                 pytest + synthetic BTS-shaped fixture (not real data)
```

## Out of scope / future work

Weather-delay analysis, route/distance effects, predictive modelling, an interactive Streamlit app
(stretch goal, only once the finding is solid).
