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

# Chart colours: each one has a single job everywhere in the app.
FLAGGED = "#eb6834"    # orange: flagged as disproportionate
SELECTED = "#2a78d6"   # blue: the airline or airport you picked
COMPARE = "#1baf7a"    # aqua: the comparison airline
NEUTRAL = "#b9c3d1"    # blue-grey: everything else
REFERENCE = "#8a8984"  # grey dashed: network average

MIN_CARRIER_FLIGHTS = 50_000
MIN_AIRPORT_FLIGHTS = 20_000
TABS = ["Overview", "Airline explorer", "Airport explorer", "What-if calculator"]
BOTH = "Both years"
FULL_DAY = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

st.set_page_config(page_title="Where Airlines Lose Time", page_icon="✈️", layout="wide")


@st.cache_data
def load_tables():
    return agg.load()


@st.cache_data
def views(year: str):
    """Tables for the chosen period ("Both years" or a single year)."""
    t = load_tables()
    by_airport, by_time = t["by_airport"], t["by_time"]
    if year != BOTH:
        by_airport = by_airport[by_airport["year"] == int(year)]
        by_time = by_time[by_time["year"] == int(year)]
    carriers = agg.entity_table(by_airport, "carrier", MIN_CARRIER_FLIGHTS // (1 if year == BOTH else 2))
    airports = agg.entity_table(by_airport, "origin", MIN_AIRPORT_FLIGHTS // (1 if year == BOTH else 2))
    return by_airport, by_time, carriers, airports


all_years = sorted(load_tables()["by_airport"]["year"].unique())
YEAR_OPTIONS = [BOTH] + [str(y) for y in all_years]

# ---- session state & actions ----------------------------------------------------------
defaults = {"year": BOTH, "tab": TABS[0], "airline": None, "compare": None, "airport": None,
            "wi_airlines": None, "wi_bands": ["<09:00"], "wi_close": 100, "wi_preset": "Report recommendation"}
for k, v in defaults.items():
    st.session_state.setdefault(k, v)
if st.session_state["year"] is None:  # segmented control can be cleared
    st.session_state["year"] = BOTH

by_airport, by_time, carriers, airports = views(st.session_state["year"])
net = agg.network_rate(by_airport)
flagged = carriers.index[carriers["flagged"]].tolist()
n_years = by_time["year"].nunique()
period = f"{all_years[0]}–{all_years[-1]}" if st.session_state["year"] == BOTH else st.session_state["year"]

# Keep selections valid for the current period.
if st.session_state["airline"] not in carriers.index:
    st.session_state["airline"] = flagged[0] if flagged else carriers.index[0]
if st.session_state["compare"] not in carriers.index:
    st.session_state["compare"] = None
if st.session_state["airport"] not in airports.index:
    st.session_state["airport"] = airports.index[0]
if st.session_state["wi_airlines"] is None:
    st.session_state["wi_airlines"] = list(flagged)
st.session_state["wi_airlines"] = [c for c in st.session_state["wi_airlines"] if c in carriers.index]


def open_airline(code: str) -> None:
    st.session_state["airline"] = code
    st.session_state["tab"] = "Airline explorer"


def open_airport(code: str) -> None:
    st.session_state["airport"] = code
    st.session_state["tab"] = "Airport explorer"


PRESETS = {
    "Report recommendation": (None, ["<09:00"], 100),
    "Evening bank": (None, ["17–21"], 100),
    "All day": (None, list(TIME_BANDS), 100),
    "Halfway there": (None, ["<09:00"], 50),
}


def apply_preset() -> None:
    name = st.session_state["wi_preset"]
    if name in PRESETS:
        airlines, bands, close = PRESETS[name]
        st.session_state["wi_airlines"] = list(flagged) if airlines is None else airlines
        st.session_state["wi_bands"] = bands
        st.session_state["wi_close"] = close


def run_recommendation() -> None:
    st.session_state["wi_preset"] = "Report recommendation"
    apply_preset()
    st.session_state["tab"] = "What-if calculator"


def custom_preset() -> None:
    st.session_state["wi_preset"] = None


# ---- chart helpers --------------------------------------------------------------------
def hbar(df: pd.DataFrame, labels: list[str], flagged_codes: set[str], xlabel: str,
         selected: str | None = None, key: str | None = None, on_select=None):
    df = df.iloc[::-1]
    labels = labels[::-1]
    colors = [SELECTED if code == selected else FLAGGED if code in flagged_codes else NEUTRAL for code in df.index]
    text = [f"{v:.1f}" if (code in flagged_codes or code == selected) else "" for code, v in zip(df.index, df["min_per_flight"])]
    fig = go.Figure(
        go.Bar(
            x=df["min_per_flight"], y=labels, orientation="h", marker_color=colors,
            text=text, textposition="outside", cliponaxis=False,
            customdata=df[["flights", "index"]].to_numpy(),
            hovertemplate="<b>%{y}</b><br>%{x:.1f} min per flight<br>%{customdata[1]:.2f}× network average"
            "<br>%{customdata[0]:,} flights<extra></extra>",
        )
    )
    fig.add_vline(x=net, line_dash="dash", line_color=REFERENCE, line_width=1,
                  annotation_text=f"Network average {net:.1f}", annotation_position="top")
    fig.update_layout(
        height=28 * len(df) + 110, margin=dict(l=10, r=40, t=30, b=40),
        xaxis_title=xlabel, bargap=0.3, showlegend=False, clickmode="event+select", dragmode=False,
    )
    kwargs = dict(width="stretch", config={"displayModeBar": False})
    if key:
        kwargs.update(key=key, on_select=on_select, selection_mode="points")
    return st.plotly_chart(fig, **kwargs)


def profile(series: dict[str, tuple[pd.Series, str, str]], x_title: str, ticktext: list[str] | None = None):
    fig = go.Figure()
    for name, (s, color, dash) in series.items():
        fig.add_trace(
            go.Scatter(
                x=s.index, y=s.values, name=name, mode="lines+markers",
                line=dict(color=color, width=2, dash=dash), marker=dict(size=7),
                hovertemplate=f"{name}: %{{y:.1f}} min<extra></extra>",
            )
        )
    fig.update_layout(
        height=340, margin=dict(l=10, r=10, t=30, b=40), xaxis_title=x_title,
        yaxis_title="min per flight", yaxis_rangemode="tozero", hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
    )
    if ticktext:
        fig.update_xaxes(tickvals=list(range(len(ticktext))), ticktext=ticktext)
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})


def pick_from_chart(chart_key: str, codes_by_label: dict[str, str], action) -> None:
    """on_select callback: open the bar that was clicked."""
    points = st.session_state[chart_key].selection.get("points", [])
    if points and points[0].get("y") in codes_by_label:
        action(codes_by_label[points[0]["y"]])


def compare_word(ratio: float) -> str:
    if ratio >= 1.05:
        return f"**{ratio - 1:.0%} more** than"
    if ratio <= 0.95:
        return f"**{1 - ratio:.0%} less** than"
    return "about the same as"


# ---- sidebar: how to use, period, glossary --------------------------------------------
with st.sidebar:
    st.header("How to use this site")
    st.markdown(
        "1. **Overview**: the big picture. Click any bar to open that airline.\n"
        "2. **Airline explorer**: pick an airline (and one to compare) to see *when* it loses time and *where*.\n"
        "3. **Airport explorer**: click an airport to see which airlines cause its delay.\n"
        "4. **What-if calculator**: choose a fix and see how many delay hours a year it would save.\n\n"
        "Hover over any chart for exact numbers."
    )
    st.segmented_control("Period", YEAR_OPTIONS, key="year",
                         help="Look at both years together, or one year on its own.")
    with st.expander("What the numbers mean"):
        st.markdown(
            "- **Carrier-attributable delay**: delay caused inside the airline's own operation: maintenance, crew, "
            "cleaning, fuelling, baggage. Not weather or air traffic control. Not the same as 'mechanical' delay.\n"
            "- **Min per flight**: carrier-attributable delay minutes, averaged over every completed flight.\n"
            "- **× network**: compared with all airlines together. 1.5× = 50% worse than average.\n"
            "- **vs others at same airports**: compared with other airlines at the same airports, so no one is "
            "penalised for flying from difficult airports.\n"
            "- **Flagged** (orange): at least 1.2× the network on every test, in every year.\n"
            "- **Excess hours / yr**: delay hours above what the network average rate would give.\n"
            "- **First wave**: departures scheduled before 09:00."
        )
    st.caption(
        "Data: US DOT Bureau of Transportation Statistics, On-Time Performance, 13.8M completed US domestic flights. "
        "This analysis uses BTS data because CAAS/data.gov.sg only publishes aggregate monthly figures for Changi — "
        "no flight-level, cause-coded delay data is publicly available."
    )

# ---- header ---------------------------------------------------------------------------
st.title("✈️ Where airlines lose time")
st.markdown(
    "Which US airlines and airports have **more delay inside their own control** than everyone else, and when "
    f"does it happen? Based on every US domestic flight, {period}."
)

with st.container(border=True):
    st.markdown("**New here? Start with one of these:**")
    q1, q2, q3 = st.columns(3)
    worst = carriers.index[0]
    q1.button(f"🔍 Why is {CARRIER_NAMES.get(worst, worst).replace(' (regional)', '')} the worst airline?",
              on_click=open_airline, args=(worst,), width="stretch")
    worst_airport = airports.index[0]
    q2.button(f"🛫 What's going wrong at {airport_cities().get(worst_airport, worst_airport).split(',')[0]}?",
              on_click=open_airport, args=(worst_airport,), width="stretch")
    q3.button("💡 What would the fix be worth?", on_click=run_recommendation, width="stretch")
    st.caption("Step-by-step instructions and a glossary of the numbers are in the sidebar (tap » on a phone).")

tab_overview, tab_airline, tab_airport, tab_whatif = st.tabs(TABS, key="tab", on_change="rerun")

# ---- overview -------------------------------------------------------------------------
with tab_overview:
    first_wave = sum(agg.what_if(by_time, c, ["<09:00"]) for c in flagged)
    c1, c2, c3 = st.columns(3)
    c1.metric("Network average", f"{net:.1f} min", help="Carrier-attributable delay per completed flight", border=True)
    c2.metric("Airlines flagged", len(flagged), help=", ".join(carrier_label(c) for c in flagged), border=True)
    c3.metric("First-wave fix (flagged airlines)", f"{round(first_wave, -2):,.0f} h / yr", border=True,
              help="Delay hours a year removed if their pre-09:00 departures matched the network's pre-09:00 rate")

    st.subheader("Which airlines lose the most time to their own delays?")
    st.caption("🟠 Orange = flagged: at least 1.2× the network average overall, in every year, and against other "
               "airlines at the same airports. **Click a bar to explore that airline.**")
    labels = [carrier_label(c) for c in carriers.index]
    hbar(carriers, labels, set(flagged), "Carrier-attributable delay (min per flight)",
         key="overview_chart", on_select=lambda: pick_from_chart("overview_chart", dict(zip(labels, carriers.index)), open_airline))
    if flagged:
        names = " and ".join(CARRIER_NAMES.get(c, c).replace(" (regional)", "") for c in flagged)
        worst_bands = {agg.band_table(by_time, c)["excess_hours_per_year"].idxmax() for c in flagged}
        timing = ("Their biggest gap is in the first flights of the day, before 09:00. Fixing that is worth the hours "
                  "shown above." if worst_bands == {"<09:00"} else "Open them in the Airline explorer to see when they "
                  "lose the most time.")
        st.info(f"**Takeaway:** {names} stand out. {timing} Try the **What-if calculator** to test other fixes.")

# ---- airline explorer -----------------------------------------------------------------
with tab_airline:
    options = carriers.index.tolist()
    a1, a2 = st.columns([2, 2])
    a1.selectbox("Airline", options, key="airline", format_func=carrier_label)
    code = st.session_state["airline"]
    a2.selectbox("Compare with (optional)", [None] + [c for c in options if c != code], key="compare",
                 format_func=lambda c: "— none —" if c is None else carrier_label(c), placeholder="— none —")
    compare = st.session_state["compare"]
    row = carriers.loc[code]
    name = CARRIER_NAMES.get(code, code).replace(" (regional)", "")

    with st.container(border=True):
        st.markdown(
            f"**In plain English:** {name} averages **{row['min_per_flight']:.1f} minutes** of delay in its own control per "
            f"flight, {compare_word(row['index'])} the average airline ({net:.1f} min). Against other airlines at the "
            f"same airports it's {compare_word(row['adj_index'])} them."
            + (" 🟠 **Flagged.**" if row["flagged"] else "")
        )
    m = st.columns(4)
    m[0].metric("Delay per flight", f"{row['min_per_flight']:.1f} min", f"{row['min_per_flight'] - net:+.1f} vs network",
                delta_color="inverse", border=True)
    m[1].metric("vs network", f"{row['index']:.2f}×", border=True, help="1.00× = exactly average")
    m[2].metric("vs others at same airports", f"{row['adj_index']:.2f}×", border=True,
                help="Compared with other airlines flying from the same airports")
    m[3].metric("Excess delay", f"{round(row['excess_hours_per_year'], -2):,.0f} h / yr", border=True,
                help="Delay hours a year above what the network average rate would give")
    year_cols = [c for c in carriers.columns if c.startswith("index_")]
    if len(year_cols) > 1:
        st.caption("By year: " + " · ".join(f"{c[-4:]}: {row[c]:.2f}× network" for c in year_cols))

    series_h = {name: (agg.hour_profile(by_time, code).loc[5:23], SELECTED, "solid")}
    series_d = {name: (agg.weekday_profile(by_time, code), SELECTED, "solid")}
    if compare:
        cname = CARRIER_NAMES.get(compare, compare).replace(" (regional)", "")
        series_h[cname] = (agg.hour_profile(by_time, compare).loc[5:23], COMPARE, "solid")
        series_d[cname] = (agg.weekday_profile(by_time, compare), COMPARE, "solid")
    series_h["All airlines"] = (agg.hour_profile(by_time).loc[5:23], REFERENCE, "dash")
    series_d["All airlines"] = (agg.weekday_profile(by_time), REFERENCE, "dash")

    left, right = st.columns(2)
    with left:
        st.markdown("**When in the day?** (scheduled departure hour)")
        profile(series_h, "Scheduled departure hour (local)")
    with right:
        st.markdown("**Which day of the week?**")
        profile(series_d, "", ticktext=DAY_NAMES)

    bands = agg.band_table(by_time, code)
    worst_band = bands["vs_network"].idxmax()
    st.markdown(f"**Gap to the network in each time band.** Worst: **{worst_band}** "
                f"({bands.loc[worst_band, 'vs_network']:.2f}× the network).")
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
            "× network": st.column_config.ProgressColumn(format="%.2f×", min_value=0,
                                                         max_value=float(max(2.0, bands["vs_network"].max()))),
            "Excess hours / yr": st.column_config.NumberColumn(format="localized"),
        },
    )

    st.markdown(f"**Where is it worst?** {name} vs other airlines at the same airport")
    st.caption("Airports where both this airline and the other airlines have at least 2,000 departures, worst gap first.")
    here = by_airport.assign(mine=by_airport["carrier"] == code)
    g = here.groupby(["origin", "mine"])[["flights", "carrier_delay"]].sum().unstack("mine").dropna()
    min_station = 2_000 // (1 if n_years > 1 else 2)
    station = pd.DataFrame({
        "Airport": [airport_label(a) for a in g.index],
        "Departures": g[("flights", True)].astype(int).to_numpy(),
        "Min per flight": (g[("carrier_delay", True)] / g[("flights", True)]).to_numpy(),
        "Others at airport": (g[("carrier_delay", False)] / g[("flights", False)]).to_numpy(),
        "_others_n": g[("flights", False)].to_numpy(),
    })
    station["× others"] = station["Min per flight"] / station["Others at airport"]
    station = station[(station["Departures"] >= min_station) & (station["_others_n"] >= min_station)]
    station = station.drop(columns="_others_n").sort_values("× others", ascending=False).head(10)
    st.dataframe(
        station, hide_index=True, width="stretch",
        column_config={
            "Departures": st.column_config.NumberColumn(format="localized"),
            "Min per flight": st.column_config.NumberColumn(format="%.1f"),
            "Others at airport": st.column_config.NumberColumn(format="%.1f"),
            "× others": st.column_config.NumberColumn(format="%.2f×"),
        },
    )

# ---- airport explorer -----------------------------------------------------------------
with tab_airport:
    st.subheader("Airports with the most carrier-attributable delay per departure")
    st.caption(f"Top 15 of {len(airports)} airports with enough departures. 🟠 Orange = flagged on every test, "
               "🔵 blue = the airport you picked. **Click a bar to pick an airport.**")
    top = airports.head(15)
    top_labels = [airport_label(a) for a in top.index]
    hbar(top, top_labels, set(airports.index[airports["flagged"]]), "Carrier-attributable delay (min per departure)",
         selected=st.session_state["airport"], key="airport_chart",
         on_select=lambda: pick_from_chart("airport_chart", dict(zip(top_labels, top.index)), open_airport))

    st.selectbox("Or search for any airport", airports.index.tolist(), key="airport", format_func=airport_label)
    code = st.session_state["airport"]
    row = airports.loc[code]
    city = airport_cities().get(code, code)
    here = by_airport[by_airport["origin"] == code].groupby("carrier")[["flights", "carrier_delay"]].sum()
    here["min_per_flight"] = here["carrier_delay"] / here["flights"]
    here["index"] = here["min_per_flight"] / net
    here = here.sort_values("min_per_flight", ascending=False)
    biggest = (here["carrier_delay"] / here["carrier_delay"].sum()).idxmax()
    with st.container(border=True):
        st.markdown(
            f"**In plain English:** departures from {city} average **{row['min_per_flight']:.1f} minutes** of "
            f"carrier-attributable delay, {compare_word(row['index'])} the network. The airline behind the most of it is "
            f"**{CARRIER_NAMES.get(biggest, biggest)}** "
            f"({here.loc[biggest, 'carrier_delay'] / here['carrier_delay'].sum():.0%} of the delay minutes here)."
            + (" 🟠 **Flagged.**" if row["flagged"] else "")
        )
    m = st.columns(3)
    m[0].metric("Delay per departure", f"{row['min_per_flight']:.1f} min", border=True)
    m[1].metric("vs network", f"{row['index']:.2f}×", border=True)
    m[2].metric("vs same airlines elsewhere", f"{row['adj_index']:.2f}×", border=True,
                help="Compared with the same airlines at other airports")
    st.markdown(f"**Airlines at {city}.** Click a bar to explore that airline.")
    here_labels = [carrier_label(c) for c in here.index]
    hbar(here, here_labels, set(flagged), "Carrier-attributable delay (min per departure)", key="airport_airlines",
         on_select=lambda: pick_from_chart("airport_airlines", dict(zip(here_labels, here.index)), open_airline))

# ---- what-if --------------------------------------------------------------------------
with tab_whatif:
    st.subheader("What would fixing it be worth?")
    st.markdown("Start from a preset, or pick airlines and departure times yourself, then slide how much of the gap "
                "to the network average they close.")
    st.pills("Presets", list(PRESETS), key="wi_preset", on_change=apply_preset)
    w1, w2 = st.columns(2)
    w1.multiselect("Airlines", carriers.index.tolist(), key="wi_airlines", format_func=carrier_label,
                   on_change=custom_preset)
    w2.multiselect("Scheduled departure", list(TIME_BANDS), key="wi_bands", on_change=custom_preset)
    st.slider("Share of the gap closed", 0, 100, step=10, format="%d%%", key="wi_close", on_change=custom_preset)
    picked, picked_bands = st.session_state["wi_airlines"], st.session_state["wi_bands"]
    close = st.session_state["wi_close"] / 100

    rows = []
    for c in picked:
        b = agg.band_table(by_time, c)
        sel = b.loc[picked_bands] if picked_bands else b.iloc[0:0]
        rows.append({
            "Airline": carrier_label(c),
            "× network in chosen bands": (sel["min_per_flight"] * sel["flights"]).sum()
            / (sel["network_min_per_flight"] * sel["flights"]).sum() if len(sel) else None,
            "Flights / yr": round(sel["flights"].sum() / n_years),
            "Hours saved / yr": agg.what_if(by_time, c, picked_bands, close),
        })
    total = sum(r["Hours saved / yr"] for r in rows)
    with st.container(border=True):
        r1, r2 = st.columns([1, 2])
        r1.metric("Carrier-attributable delay removed", f"{round(total, -2):,.0f} hours a year")
        if total > 0:
            r2.markdown(
                f"That's about **{total / 365:,.0f} hours of delay every day**, or roughly "
                f"**{total * 60 / max(1, sum(r['Flights / yr'] for r in rows)):.1f} minutes** off each affected flight."
            )
        elif picked and picked_bands:
            r2.markdown("These airlines are already at or better than the network in those times, so there's nothing to "
                        "recover.")
        else:
            r2.markdown("Pick at least one airline and one departure time.")
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
    "Cause minutes are only recorded for flights 15+ minutes late and are self-reported by airlines."
)
