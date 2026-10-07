"""Interactive companion to the report: explore carrier-attributable delay by
airline, airport and time, and size the first-wave recommendation.

    streamlit run app/streamlit_app.py

Reads only the small tables in app/aggregates/ (rebuild with
`python scripts/build_app_data.py`), so it runs without the 85 MB dataset.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from aviation_delays import aggregates as agg  # noqa: E402
from aviation_delays.data import CARRIER_NAMES, DAY_NAMES, airport_cities, airport_label, carrier_label  # noqa: E402
from aviation_delays.metrics import TIME_BANDS  # noqa: E402

HIGHLIGHT = "#2a78d6"
NEUTRAL = "#c3c2b7"
REFERENCE = "#8a8984"
MIN_CARRIER_FLIGHTS = 50_000
MIN_AIRPORT_FLIGHTS = 20_000

st.set_page_config(page_title="Where Airlines Lose Time", page_icon="✈️", layout="wide")


@st.cache_data
def load():
    t = agg.load()
    years = sorted(t["by_airport"]["year"].unique())
    return (
        t,
        agg.entity_table(t["by_airport"], "carrier", MIN_CARRIER_FLIGHTS),
        agg.entity_table(t["by_airport"], "origin", MIN_AIRPORT_FLIGHTS),
        years,
    )


tables, carriers, airports, years = load()
by_airport, by_time = tables["by_airport"], tables["by_time"]
net = agg.network_rate(by_airport)
flagged = carriers.index[carriers["flagged"]].tolist()
period = f"{years[0]}–{years[-1]}"


def hbar(df: pd.DataFrame, labels: list[str], highlight: set[str], xlabel: str, height: int | None = None) -> go.Figure:
    df = df.iloc[::-1]
    labels = labels[::-1]
    fig = go.Figure(
        go.Bar(
            x=df["min_per_flight"],
            y=labels,
            orientation="h",
            marker_color=[HIGHLIGHT if code in highlight else NEUTRAL for code in df.index],
            customdata=df[["flights", "index"]].to_numpy(),
            hovertemplate="<b>%{y}</b><br>%{x:.1f} min per flight<br>%{customdata[1]:.2f}× network"
            "<br>%{customdata[0]:,} flights<extra></extra>",
        )
    )
    fig.add_vline(x=net, line_dash="dash", line_color=REFERENCE, line_width=1,
                  annotation_text="Network average", annotation_position="top")
    fig.update_layout(
        height=height or 28 * len(df) + 110, margin=dict(l=10, r=20, t=30, b=40),
        xaxis_title=xlabel, bargap=0.3, showlegend=False,
    )
    return fig


def profile(series: dict[str, pd.Series], x_title: str, ticktext: list[str] | None = None) -> go.Figure:
    fig = go.Figure()
    for name, s in series.items():
        is_network = name == "All airlines"
        fig.add_trace(
            go.Scatter(
                x=s.index, y=s.values, name=name, mode="lines+markers",
                line=dict(color=REFERENCE if is_network else HIGHLIGHT, width=2, dash="dash" if is_network else "solid"),
                marker=dict(size=7),
                hovertemplate=f"{name}<br>%{{y:.1f}} min per flight<extra></extra>",
            )
        )
    fig.update_layout(
        height=340, margin=dict(l=10, r=10, t=30, b=40), xaxis_title=x_title,
        yaxis_title="min per flight", yaxis_rangemode="tozero", hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
    )
    if ticktext:
        fig.update_xaxes(tickvals=list(range(len(ticktext))), ticktext=ticktext)
    return fig


# ---- header -----------------------------------------------------------------------
st.title("Where airlines lose time")
st.markdown(
    "Carrier-attributable delay in US domestic flights: delay inside the airline's own control "
    "(maintenance, crew, cleaning, fuelling, baggage). It is **not** a mechanical-delay measure. "
    f"BTS On-Time Performance data, {period}."
)
st.caption(
    "This analysis uses US DOT (BTS) flight data rather than Singapore data, since CAAS/data.gov.sg only publishes "
    "aggregate monthly figures for Changi — no flight-level, cause-coded delay data is publicly available."
)

tab_overview, tab_airline, tab_airport, tab_whatif = st.tabs(
    ["Overview", "Airline explorer", "Airport explorer", "What-if calculator"]
)

# ---- overview ---------------------------------------------------------------------
with tab_overview:
    first_wave = sum(agg.what_if(by_time, c, ["<09:00"]) for c in flagged)
    c1, c2, c3 = st.columns(3)
    c1.metric("Network average", f"{net:.1f} min", help="Carrier-attributable delay per completed flight")
    c2.metric("Airlines flagged", len(flagged), help=", ".join(carrier_label(c) for c in flagged))
    c3.metric("First-wave fix (flagged airlines)", f"{round(first_wave, -2):,.0f} h / yr",
              help="Delay hours a year removed if their pre-09:00 departures matched the network's pre-09:00 rate")
    st.subheader("Carrier-attributable delay per flight, by airline")
    st.caption(
        f"Highlighted: ≥{agg.FLAG_INDEX}× the network rate overall, in every year, and against other airlines at the same "
        "airports."
    )
    st.plotly_chart(
        hbar(carriers, [carrier_label(c) for c in carriers.index], set(flagged), "Carrier-attributable delay (min per flight)"),
        width="stretch",
    )

# ---- airline explorer -------------------------------------------------------------
with tab_airline:
    options = carriers.index.tolist()
    code = st.selectbox(
        "Airline", options, index=options.index(flagged[0]) if flagged else 0, format_func=carrier_label
    )
    row = carriers.loc[code]
    m = st.columns(4)
    m[0].metric("Delay per flight", f"{row['min_per_flight']:.1f} min", f"{row['min_per_flight'] - net:+.1f} vs network",
                delta_color="inverse")
    m[1].metric("vs network", f"{row['index']:.2f}×")
    m[2].metric("vs others at same airports", f"{row['adj_index']:.2f}×")
    m[3].metric("Excess delay", f"{round(row['excess_hours_per_year'], -2):,.0f} h / yr")
    st.caption(" · ".join(f"{y}: {row[f'index_{y}']:.2f}× network" for y in years)
               + (" · **flagged**" if row["flagged"] else ""))

    left, right = st.columns(2)
    with left:
        st.markdown("**By scheduled departure hour**")
        hours = agg.hour_profile(by_time, code).loc[5:23]
        st.plotly_chart(
            profile({CARRIER_NAMES.get(code, code): hours, "All airlines": agg.hour_profile(by_time).loc[5:23]},
                    "Scheduled departure hour (local)"),
            width="stretch",
        )
    with right:
        st.markdown("**By day of week**")
        st.plotly_chart(
            profile({CARRIER_NAMES.get(code, code): agg.weekday_profile(by_time, code),
                     "All airlines": agg.weekday_profile(by_time)}, "", ticktext=DAY_NAMES),
            width="stretch",
        )

    st.markdown("**Gap to the network in each time band**")
    bands = agg.band_table(by_time, code)
    st.dataframe(
        bands.assign(excess_hours_per_year=bands["excess_hours_per_year"].round()).reset_index().rename(columns={
            "band": "Scheduled departure", "flights": "Flights", "min_per_flight": "Min per flight",
            "network_min_per_flight": "Network min per flight", "vs_network": "× network",
            "excess_hours_per_year": "Excess hours / yr"}),
        hide_index=True, width="stretch",
        column_config={
            "Flights": st.column_config.NumberColumn(format="localized"),
            "Min per flight": st.column_config.NumberColumn(format="%.1f"),
            "Network min per flight": st.column_config.NumberColumn(format="%.1f"),
            "× network": st.column_config.NumberColumn(format="%.2f×"),
            "Excess hours / yr": st.column_config.NumberColumn(format="localized"),
        },
    )

    st.markdown("**Where it's worst: this airline vs other airlines at the same airport**")
    st.caption("Airports where both this airline and the other airlines have at least 2,000 departures, sorted by the gap.")
    here = by_airport.assign(mine=by_airport["carrier"] == code)
    g = here.groupby(["origin", "mine"])[["flights", "carrier_delay"]].sum().unstack("mine")
    g = g.dropna()
    station = pd.DataFrame({
        "Airport": [airport_label(a) for a in g.index],
        "Departures": g[("flights", True)].astype(int).to_numpy(),
        "Min per flight": (g[("carrier_delay", True)] / g[("flights", True)]).to_numpy(),
        "Others at airport": (g[("carrier_delay", False)] / g[("flights", False)]).to_numpy(),
        "_others_n": g[("flights", False)].to_numpy(),
    })
    station["× others"] = station["Min per flight"] / station["Others at airport"]
    station = station[(station["Departures"] >= 2_000) & (station["_others_n"] >= 2_000)].drop(columns="_others_n")
    station = station.sort_values("× others", ascending=False).head(10)
    st.dataframe(
        station, hide_index=True, width="stretch",
        column_config={
            "Departures": st.column_config.NumberColumn(format="localized"),
            "Min per flight": st.column_config.NumberColumn(format="%.1f"),
            "Others at airport": st.column_config.NumberColumn(format="%.1f"),
            "× others": st.column_config.NumberColumn(format="%.2f×"),
        },
    )

# ---- airport explorer -------------------------------------------------------------
with tab_airport:
    st.subheader("Airports with the most carrier-attributable delay per departure")
    st.caption(
        f"Top 15 of {len(airports)} airports with ≥{MIN_AIRPORT_FLIGHTS:,} departures. Highlighted: flagged on every test."
    )
    top = airports.head(15)
    st.plotly_chart(
        hbar(top, [airport_label(a) for a in top.index], set(airports.index[airports["flagged"]]),
             "Carrier-attributable delay (min per departure)"),
        width="stretch",
    )
    options = airports.index.tolist()
    code = st.selectbox("Airport", options, format_func=airport_label)
    row = airports.loc[code]
    m = st.columns(3)
    m[0].metric("Delay per departure", f"{row['min_per_flight']:.1f} min")
    m[1].metric("vs network", f"{row['index']:.2f}×")
    m[2].metric("vs same airlines elsewhere", f"{row['adj_index']:.2f}×")
    here = by_airport[by_airport["origin"] == code].groupby("carrier")[["flights", "carrier_delay"]].sum()
    here["min_per_flight"] = here["carrier_delay"] / here["flights"]
    here["index"] = here["min_per_flight"] / net
    here = here.sort_values("min_per_flight", ascending=False)
    st.markdown(f"**Airlines at {airport_cities().get(code, code)}**")
    st.plotly_chart(
        hbar(here, [carrier_label(c) for c in here.index], set(flagged), "Carrier-attributable delay (min per departure)"),
        width="stretch",
    )

# ---- what-if ----------------------------------------------------------------------
with tab_whatif:
    st.subheader("What would fixing it be worth?")
    st.markdown(
        "Pick airlines and departure times, then choose how much of the gap to the network rate they close. "
        "The defaults reproduce the report's recommendation: the flagged airlines fully close their pre-09:00 gap."
    )
    picked = st.multiselect("Airlines", carriers.index.tolist(), default=flagged, format_func=carrier_label)
    picked_bands = st.multiselect("Scheduled departure", list(TIME_BANDS), default=["<09:00"])
    close = st.slider("Share of the gap closed", 0, 100, 100, step=10, format="%d%%") / 100

    rows = []
    for c in picked:
        b = agg.band_table(by_time, c)
        rows.append({
            "Airline": carrier_label(c),
            "× network in chosen bands": (b.loc[picked_bands, "min_per_flight"] * b.loc[picked_bands, "flights"]).sum()
            / (b.loc[picked_bands, "network_min_per_flight"] * b.loc[picked_bands, "flights"]).sum() if picked_bands else None,
            "Flights / yr": round(b.loc[picked_bands, "flights"].sum() / len(years)),
            "Hours saved / yr": agg.what_if(by_time, c, picked_bands, close),
        })
    total = sum(r["Hours saved / yr"] for r in rows)
    st.metric("Carrier-attributable delay removed", f"{round(total, -2):,.0f} hours a year")
    if rows:
        st.dataframe(
            pd.DataFrame(rows).round({"Hours saved / yr": 0}), hide_index=True, width="stretch",
            column_config={
                "× network in chosen bands": st.column_config.NumberColumn(format="%.2f×"),
                "Flights / yr": st.column_config.NumberColumn(format="localized"),
                "Hours saved / yr": st.column_config.NumberColumn(format="localized"),
            },
        )
    st.caption(
        "Conservative: a late early flight also delays the aircraft's later flights, which BTS books as "
        "late-arriving-aircraft delay and which isn't counted here. Airlines already better than the network in a band "
        "count as zero."
    )

st.divider()
st.caption(
    "Source: US DOT Bureau of Transportation Statistics, Reporting Carrier On-Time Performance. "
    "Cause minutes are only recorded for flights 15+ minutes late and are self-reported by airlines. "
    "Full method in the report."
)
