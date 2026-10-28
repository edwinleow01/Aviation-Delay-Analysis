"""Interactive companion to the report: explore carrier-attributable delay by
airline, airport and time, and size the first-wave recommendation.

    streamlit run app/streamlit_app.py

Reads only the small tables in app/aggregates/ (rebuild with
`python scripts/build_app_data.py`), so it runs without the 85 MB dataset.
Fonts and the US map outline are served from app/static/.
Optional: put your own photo at app/assets/hero.jpg (and a one-line caption in
app/assets/hero_caption.txt) to show it under the title.
"""

from __future__ import annotations

import html
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

APP_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(APP_DIR.parent / "src"))
from aviation_delays import aggregates as agg  # noqa: E402
from aviation_delays.data import (  # noqa: E402
    CARRIER_NAMES, DAY_NAMES, airport_cities, airport_coords, airport_label, carrier_label,
)
from aviation_delays.metrics import TIME_BANDS  # noqa: E402

REPORT_PDF = APP_DIR.parent / "report" / "aviation_delay_report.pdf"

# Chart colours: each one has a single job everywhere in the app.
FLAGGED = "#eb6834"    # orange: flagged as disproportionate
FLAGGED_2 = "#a8431a"  # dark orange: second flagged airline when two share a chart
FLAGGED_MORE = [FLAGGED, FLAGGED_2, "#f4a06f", "#6e2b10", "#c95a2a"]  # oranges, one per flagged airline
SELECTED = "#2a78d6"   # blue: the airline or airport you picked
COMPARE = "#1baf7a"    # aqua: the comparison airline
NEUTRAL = "#b9c3d1"    # blue-grey: everything else
REFERENCE = "#8a8984"  # grey dashed: network average
MAP_SCALE = [[0.0, "#2a78d6"], [0.5, "#c9ced6"], [1.0, "#eb6834"]]  # better ↔ average ↔ worse

MIN_CARRIER_FLIGHTS = 50_000
MIN_AIRPORT_FLIGHTS = 20_000
TABS = ["Findings", "Airlines", "Airports", "What if", "Method & report"]
BOTH = "Both years"
PLOTLY_CONFIG = {"displayModeBar": False, "topojsonURL": "app/static/"}

st.set_page_config(page_title="Where Airlines Lose Time", page_icon="✈️", layout="wide")

st.html("""
<style>
  .kicker { font-size: .78rem; letter-spacing: .12em; text-transform: uppercase; opacity: .7; margin: 0 0 .2rem; }
  .standfirst { font-size: 1.18rem; line-height: 1.55; margin: .2rem 0 .6rem; max-width: 40rem; }
  .byline { font-size: .88rem; opacity: .7; margin-bottom: .4rem; }
  .lead { font-size: 1.08rem; line-height: 1.6; max-width: 46rem; }
  .finding-no { font-family: "JetBrains Mono", monospace; font-size: .8rem; letter-spacing: .1em; opacity: .65; }
  .pull { font-family: "SourceSerif", serif; font-size: 2.6rem; font-weight: 700; line-height: 1.05; }
  .pull-label { font-size: .9rem; opacity: .75; }
  .toc { font-size: .9rem; margin: .4rem 0 .2rem; }
  .toc a { margin-right: 1.1rem; text-decoration: none; }
  .toc a:hover { text-decoration: underline; }
</style>
""")


# ---- data -----------------------------------------------------------------------------
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
    scale = 1 if year == BOTH else 2
    carriers = agg.entity_table(by_airport, "carrier", MIN_CARRIER_FLIGHTS // scale)
    airports = agg.entity_table(by_airport, "origin", MIN_AIRPORT_FLIGHTS // scale)
    return by_airport, by_time, carriers, airports


all_years = sorted(load_tables()["by_airport"]["year"].unique())
YEAR_OPTIONS = [BOTH] + [str(y) for y in all_years]

# ---- session state & actions ----------------------------------------------------------
defaults = {"year": BOTH, "tab": TABS[0], "airline": None, "compare": None, "airport": None,
            "wi_airlines": None, "wi_bands": ["<09:00"], "wi_close": 100, "wi_preset": "The recommendation"}
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


def short(code: str) -> str:
    return CARRIER_NAMES.get(code, code).replace(" (regional)", "")


def open_airline(code: str) -> None:
    st.session_state["airline"] = code
    st.session_state["tab"] = "Airlines"


def open_airport(code: str) -> None:
    st.session_state["airport"] = code
    st.session_state["tab"] = "Airports"


PRESETS = {
    "The recommendation": (["<09:00"], 100),
    "Evening (17:00–21:00)": (["17–21"], 100),
    "All day": (list(TIME_BANDS), 100),
    "Halfway there": (["<09:00"], 50),
}


def apply_preset() -> None:
    name = st.session_state["wi_preset"]
    if name in PRESETS:
        bands, close = PRESETS[name]
        st.session_state["wi_airlines"] = list(flagged)
        st.session_state["wi_bands"] = bands
        st.session_state["wi_close"] = close


def run_recommendation() -> None:
    st.session_state["wi_preset"] = "The recommendation"
    apply_preset()
    st.session_state["tab"] = "What if"


def custom_preset() -> None:
    st.session_state["wi_preset"] = None


BAND_WORDS = {"<09:00": "before 09:00", "09–13": "09:00–13:00", "13–17": "13:00–17:00", "17–21": "17:00–21:00",
              "21+": "after 21:00"}


def joined(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def higher_lower(ratio: float) -> str:
    """'54% higher' / '12% lower' / 'about the same'."""
    if ratio >= 1.05:
        return f"{ratio - 1:.0%} higher"
    if ratio <= 0.95:
        return f"{1 - ratio:.0%} lower"
    return "about the same"


def compare_word(ratio: float) -> str:
    if ratio >= 1.05:
        return f"**{ratio - 1:.0%} more** than"
    if ratio <= 0.95:
        return f"**{1 - ratio:.0%} less** than"
    return "about the same as"


# ---- graphics -------------------------------------------------------------------------
def departures_board(rows: pd.DataFrame, title: str, limit: int = 8) -> str:
    """An airport departures board (FIDS) listing airlines by carrier-attributable delay."""
    body = []
    for i, (code, r) in enumerate(rows.head(limit).iterrows()):
        if r["flagged"]:
            status, cls = "FLAGGED", "flag"
        elif r["index"] > 1.0:
            status, cls = "ABOVE AVG", "late"
        else:
            status, cls = "BELOW AVG", "ok"
        body.append(
            f'<tr style="animation-delay:{i * 70}ms"><td>{html.escape(short(code).upper())}</td><td>{code}</td>'
            f'<td class="num">{r["min_per_flight"]:.1f}</td><td class="num">{r["index"]:.2f}×</td>'
            f'<td><span class="st {cls}">{status}</span></td></tr>'
        )
    more = len(rows) - limit
    return f"""
<style>
  .fids {{ background:#0c0e11; color:#eef1f4; border-radius:10px; padding:14px 16px 10px;
          font-family:"JetBrains Mono",ui-monospace,monospace; box-shadow:0 8px 24px rgba(0,0,0,.18); }}
  .fids .top {{ display:flex; justify-content:space-between; align-items:baseline; gap:12px;
               border-bottom:1px solid #2a2f37; padding-bottom:8px; margin-bottom:4px; }}
  .fids .top b {{ color:#ffd23f; letter-spacing:.14em; font-size:.95rem; }}
  .fids .top span {{ color:#9aa3ad; font-size:.72rem; letter-spacing:.06em; text-align:right; }}
  .fids table {{ width:100%; border-collapse:collapse; font-size:.82rem; letter-spacing:.05em; }}
  .fids th {{ color:#9aa3ad; font-weight:500; font-size:.66rem; text-align:left; padding:6px 4px 4px; letter-spacing:.1em; }}
  .fids td {{ padding:6px 4px; border-top:1px solid #1d2128; white-space:nowrap; }}
  .fids .num, .fids th.num {{ text-align:right; }}
  .fids tr {{ animation: flap .45s ease-out both; }}
  .fids .st {{ padding:2px 6px; border-radius:3px; font-weight:700; font-size:.7rem; }}
  .fids .flag {{ background:#ffd23f; color:#0c0e11; }}
  .fids .late {{ color:#ffd23f; }}
  .fids .ok {{ color:#7fd6a4; }}
  .fids .foot {{ color:#7c858f; font-size:.68rem; padding-top:8px; }}
  @keyframes flap {{ from {{ opacity:0; transform: rotateX(70deg); }} to {{ opacity:1; transform:none; }} }}
  @media (prefers-reduced-motion: reduce) {{ .fids tr {{ animation:none; }} }}
</style>
<div class="fids" role="img" aria-label="Departures board ranking airlines by carrier-attributable delay">
  <div class="top"><b>DEPARTURES</b><span>{html.escape(title)}<br>NETWORK AVG {net:.1f} MIN</span></div>
  <table>
    <thead><tr><th>AIRLINE</th><th>CODE</th><th class="num">MIN/FLT</th><th class="num">VS AVG</th><th>STATUS</th></tr></thead>
    <tbody>{''.join(body)}</tbody>
  </table>
  <div class="foot">{f'+{more} MORE AIRLINES IN THE AIRLINES TAB' if more > 0 else ''}</div>
</div>"""


def rotation_diagram() -> str:
    """Illustration: one aircraft's day, showing why a late first departure is undercounted.
    Text is sized to stay readable when the drawing is scaled down to phone width."""
    x0, x1, t0, t1 = 84, 750, 5.6, 15.4  # px range and hours shown

    def x(h: float) -> float:
        return x0 + (h - t0) / (t1 - t0) * (x1 - x0)

    legs = [(6.0, 7.5, "DTW–ORD"), (8.25, 9.75, "ORD–MSP"), (10.5, 12.0, "MSP–DEN"), (13.0, 14.5, "DEN–SLC")]
    delays = [25, 20, 10, 0]  # minutes late at departure
    parts = []
    for h in range(6, 16, 2):
        parts.append(f'<line x1="{x(h):.1f}" y1="34" x2="{x(h):.1f}" y2="206" class="grid"/>'
                     f'<text x="{x(h):.1f}" y="230" class="tick">{h:02d}:00</text>')
    for (dep, arr, name), late in zip(legs, delays):
        parts.append(f'<rect x="{x(dep):.1f}" y="40" width="{x(arr) - x(dep):.1f}" height="34" rx="5" class="sched"/>'
                     f'<text x="{(x(dep) + x(arr)) / 2:.1f}" y="63" class="leg">{name}</text>')
        s_, e_ = dep + late / 60, arr + late / 60
        parts.append(f'<rect x="{x(s_):.1f}" y="104" width="{x(e_) - x(s_):.1f}" height="34" rx="5" class="actual"/>')
        if late:
            cls = "carrier" if late == 25 else "knock"
            parts.append(f'<rect x="{x(dep):.1f}" y="104" width="{x(s_) - x(dep):.1f}" height="34" rx="4" class="{cls}"/>')
            line2 = "carrier delay" if late == 25 else "knock-on"
            parts.append(f'<text x="{x(dep):.1f}" y="164" class="note {cls}-t">+{late} min</text>'
                         f'<text x="{x(dep):.1f}" y="184" class="note {cls}-t">{line2}</text>')
        else:
            parts.append(f'<text x="{x(dep):.1f}" y="164" class="note">back on</text>'
                         f'<text x="{x(dep):.1f}" y="184" class="note">time</text>')
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 760 244" width="760" height="244" role="img" aria-labelledby="rot-t rot-d" style="color:#7d8a9e;font-family:'Source Sans Pro','Source Sans 3',Arial,sans-serif">
  <title id="rot-t">One aircraft's day</title>
  <desc id="rot-d">A crew problem delays the first departure by 25 minutes. The aircraft then leaves 20 and 10 minutes
  late on its next two flights before turn-time buffers absorb the delay.</desc>
  <style>
    .grid {{ stroke: currentColor; stroke-opacity: .25; }}
    .tick {{ fill: currentColor; font-size: 16px; text-anchor: middle; }}
    .lane {{ fill: currentColor; font-size: 18px; font-weight: 600; }}
    .sched {{ fill: none; stroke: currentColor; stroke-opacity: .5; stroke-dasharray: 5 4; }}
    .actual {{ fill: {SELECTED}; fill-opacity: .85; }}
    .carrier {{ fill: {FLAGGED}; }}
    .knock {{ fill: {NEUTRAL}; }}
    .leg {{ fill: currentColor; font-size: 15px; text-anchor: middle; }}
    .note {{ fill: currentColor; font-size: 16px; }}
    .carrier-t {{ fill: {FLAGGED}; font-weight: 700; }}
  </style>
  <text x="0" y="63" class="lane">Plan</text>
  <text x="0" y="127" class="lane">Actual</text>
  {''.join(parts)}
</svg>"""


ROTATION_CAPTION = (
    "Illustration, not real flight data. A crew problem holds the first departure for 25 minutes; BTS books that as "
    "**carrier delay**. The same aircraft then leaves 20 and 10 minutes late on its next flights, which BTS books as "
    "**late-arriving aircraft**, so this analysis doesn't count them. Preventing the first delay would prevent those too."
)


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
    kwargs = dict(width="stretch", config=PLOTLY_CONFIG)
    if key:
        kwargs.update(key=key, on_select=on_select, selection_mode="points")
    return st.plotly_chart(fig, **kwargs)


def profile(series: dict[str, tuple[pd.Series, str, str]], x_title: str, y_title: str = "min per flight",
            ticktext: list[str] | None = None, reference: float | None = None, height: int = 340,
            label_lines: bool = False):
    fig = go.Figure()
    for name, (s, color, dash) in series.items():
        fig.add_trace(go.Scatter(
            x=s.index, y=s.values, name=name, mode="lines+markers",
            line=dict(color=color, width=2, dash=dash), marker=dict(size=7),
            hovertemplate=f"{name}: %{{y:.2f}}<extra></extra>",
        ))
        if label_lines:  # name each line where it starts, so readers don't have to match colours to the legend
            fig.add_annotation(x=s.index[0], y=s.values[0], text=f"<b>{name}</b>", showarrow=False,
                               xanchor="left", yanchor="bottom", yshift=8, font=dict(size=12))
    if reference is not None:
        fig.add_hline(y=reference, line_dash="dash", line_color=REFERENCE, line_width=1,
                      annotation_text="Network average", annotation_position="bottom right")
    fig.update_layout(
        height=height, margin=dict(l=10, r=10, t=30, b=40), xaxis_title=x_title, yaxis_title=y_title,
        yaxis_rangemode="tozero", hovermode="x unified", dragmode=False,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
    )
    if ticktext:
        fig.update_xaxes(tickvals=list(range(len(ticktext))), ticktext=ticktext)
    st.plotly_chart(fig, width="stretch", config=PLOTLY_CONFIG)


def airport_map(key: str):
    """US map of airports: bubble = departures, colour = carrier-attributable delay vs the network."""
    coords = airport_coords()
    df = airports.join(coords[["lat", "lon"]], how="inner")
    size = 6 + 26 * np.sqrt(df["flights"] / df["flights"].max())
    labels = [airport_label(c) for c in df.index]
    fig = go.Figure(go.Scattergeo(
        lat=df["lat"], lon=df["lon"], mode="markers",
        marker=dict(size=size, color=df["index"].clip(0.5, 1.5), cmin=0.5, cmax=1.5, colorscale=MAP_SCALE,
                    line=dict(width=[4 if c == st.session_state["airport"] else 0.6 for c in df.index],
                              color=[SELECTED if c == st.session_state["airport"] else "rgba(20,30,50,.45)" for c in df.index]),
                    colorbar=dict(title=dict(text="vs network", side="top"), orientation="h", thickness=10,
                                  len=0.6, x=0.5, xanchor="center", y=-0.02, yanchor="top", tickvals=[0.5, 1, 1.5],
                                  ticktext=["0.5× (better)", "1× (average)", "1.5× (worse)"])),
        text=labels, customdata=np.stack([df["min_per_flight"], df["index"], df["flights"]], axis=1),
        hovertemplate="<b>%{text}</b><br>%{customdata[0]:.1f} min per departure<br>%{customdata[1]:.2f}× network"
        "<br>%{customdata[2]:,} departures<extra></extra>",
    ))
    flag = df[df["flagged"]]
    fig.add_trace(go.Scattergeo(
        lat=flag["lat"], lon=flag["lon"], mode="text", text=list(flag.index), textposition="top center",
        textfont=dict(size=12, color=FLAGGED), hoverinfo="skip",
    ))
    fig.update_geos(scope="usa", projection_type="albers usa", bgcolor="rgba(0,0,0,0)",
                    landcolor="rgba(150,165,185,.16)", subunitcolor="rgba(150,165,185,.55)",
                    countrycolor="rgba(150,165,185,.55)", showlakes=False)
    fig.update_layout(height=520, margin=dict(l=0, r=0, t=10, b=70), showlegend=False, dragmode=False,
                      clickmode="event+select")

    def picked():
        points = st.session_state[key].selection.get("points", [])
        if points and points[0].get("curve_number", 0) == 0:
            open_airport(df.index[points[0]["point_index"]])

    st.plotly_chart(fig, width="stretch", config=PLOTLY_CONFIG, key=key, on_select=picked, selection_mode="points")


def pick_from_chart(chart_key: str, codes_by_label: dict[str, str], action) -> None:
    """on_select callback: open the bar that was clicked."""
    points = st.session_state[chart_key].selection.get("points", [])
    if points and points[0].get("y") in codes_by_label:
        action(codes_by_label[points[0]["y"]])


# ---- sidebar --------------------------------------------------------------------------
with st.sidebar:
    st.subheader("Getting around")
    st.markdown(
        "- **Findings**: the story in three charts. Short on time? Read just the bold lines.\n"
        "- **Airlines**: pick any airline, and one to compare it with.\n"
        "- **Airports**: pick any airport, or click a dot on the map.\n"
        "- **What if**: see what a fix would be worth.\n"
        "- **Method & report**: how it was done, plus the full report as a PDF.\n\n"
        "Click any bar or map dot to jump to that airline or airport. Hover over a chart for exact numbers.\n\n"
        "**Light or dark:** open the ⋮ menu (top right) and pick System, Light or Dark."
    )
    st.segmented_control("Period", YEAR_OPTIONS, key="year", help="Both years together, or one year on its own.")
    with st.expander("What the numbers mean"):
        st.markdown(
            "- **Carrier-attributable delay**: delay caused inside the airline's own operation: maintenance, crew, "
            "cleaning, fuelling, baggage. Not weather or air traffic control. Not the same as 'mechanical' delay.\n"
            "- **Min per flight**: those delay minutes averaged over every completed flight.\n"
            "- **× network**: compared with all airlines together. 1.5× = 50% worse than average.\n"
            "- **vs others at same airports**: compared with other airlines at the same airports, so no one is "
            "penalised for flying from difficult airports.\n"
            "- **Flagged**: at least 1.2× the network on every test, in every year.\n"
            "- **Excess hours / yr**: delay hours above what the network average rate would give.\n"
            "- **First wave**: departures scheduled before 09:00."
        )

# ---- header ---------------------------------------------------------------------------
first_wave = sum(agg.what_if(by_time, c, ["<09:00"]) for c in flagged)
left, right = st.columns([5, 4], gap="large")
with left:
    st.html(f'<p class="kicker">Case study · US aviation · {period} · 3-minute read</p>')
    st.title("Where airlines lose time")
    st.html(
        '<p class="standfirst">Weather and air traffic get the blame for late flights, but a third of recorded delay minutes '
        "come from inside the airline: maintenance, crew, cleaning, fuelling, baggage. Across 13.8 million US flights, "
        "which airlines and airports lose the most time this way, and when does it happen?</p>"
        '<p class="byline">Data: US DOT Bureau of Transportation Statistics</p>'
    )
    hero = APP_DIR / "assets" / "hero.jpg"
    if hero.exists():
        cap = APP_DIR / "assets" / "hero_caption.txt"
        st.image(str(hero), caption=cap.read_text().strip() if cap.exists() else None)
    st.markdown("**Start with a question**")
    worst, worst_airport = carriers.index[0], airports.index[0]
    st.button(f"Why is {short(worst)} the worst airline? →", on_click=open_airline, args=(worst,), type="tertiary")
    st.button(f"What's going wrong at {airport_cities().get(worst_airport, worst_airport).split(',')[0]}? →",
              on_click=open_airport, args=(worst_airport,), type="tertiary")
    st.button("What would fixing it be worth? →", on_click=run_recommendation, type="tertiary")
with right:
    st.html(departures_board(carriers, f"CARRIER-ATTRIBUTABLE DELAY · {period}"))

tab_findings, tab_airline, tab_airport, tab_whatif, tab_method = st.tabs(TABS, key="tab", on_change="rerun")

# ---- findings -------------------------------------------------------------------------
def back_to_both_years() -> None:
    st.session_state["year"] = BOTH


with tab_findings:
    if st.session_state["year"] != BOTH:
        n1, n2 = st.columns([5, 1], vertical_alignment="center")
        n1.info(f"You're looking at **{period} only**. The main conclusion uses both years together, which is stricter: "
                "an airline has to stand out in each year to be flagged. Single years can flag a few more airlines.")
        n2.button("Back to both years", on_click=back_to_both_years, key="both_years")
    st.html('<div class="toc"><a href="#f1">01 Airlines</a><a href="#f2">02 First flights</a>'
            '<a href="#f3">03 Airports</a><a href="#so-what">So what</a></div>')
    names = (", ".join(short(c) for c in flagged[:-1]) + " and " + short(flagged[-1])) if len(flagged) > 1 else \
        (short(flagged[0]) if flagged else "No airline")
    s1, s2, s3 = st.columns(3)
    s1.html(f'<div class="pull">{net:.1f} min</div><div class="pull-label">average carrier-attributable delay per '
            'flight, across every airline</div>')
    s2.html(f'<div class="pull">{len(flagged)} airlines</div><div class="pull-label">stand out on every test: '
            f'{names if flagged else "none"}</div>')
    s3.html(f'<div class="pull">{round(first_wave, -2):,.0f} h</div><div class="pull-label">of delay a year that '
            'fixing their first flights of the day would remove</div>')

    st.html('<p class="finding-no">FINDING 01</p>')
    plural = len(flagged) > 1
    st.subheader(f"{names} {'lose' if plural or not flagged else 'loses'} the most time to their own delays", anchor="f1")
    if flagged:
        worst_adj = min(carriers.loc[c, "adj_index"] for c in flagged)
        subject = "Both are" if len(flagged) == 2 else "All of them are" if plural else "It is"
        mins = [f"{carriers.loc[c, 'min_per_flight']:.1f}" for c in flagged]
        rates = f"{short(flagged[0])} averages {mins[0]} minutes of carrier-attributable delay per flight" + (
            ", " + joined([f"{short(c)} {m}" for c, m in zip(flagged[1:], mins[1:])]) if plural else "")
        st.markdown(
            f"**{names} {'stand' if plural else 'stands'} out, and not because of where they fly.** {rates}, against "
            f"{net:.1f} for the network. {subject} still at least {worst_adj:.1f}× the rate of other airlines flying "
            "from the same airports. Click a bar to look closer."
        )
    labels = [carrier_label(c) for c in carriers.index]
    hbar(carriers, labels, set(flagged), "Carrier-attributable delay (min per flight)", key="overview_chart",
         on_select=lambda: pick_from_chart("overview_chart", dict(zip(labels, carriers.index)), open_airline))
    st.caption("Orange = flagged: at least 1.2× the network average overall, in every year, and against other "
               "airlines at the same airports.")

    st.html('<p class="finding-no">FINDING 02</p>')
    worst_bands = {agg.band_table(by_time, c)["excess_hours_per_year"].idxmax() for c in flagged}
    first_wave_story = bool(flagged) and worst_bands == {"<09:00"}
    st.subheader("They fall furthest behind on the first flights of the day" if first_wave_story
                 else "When they fall behind", anchor="f2")
    f1, f2 = st.columns([3, 2], gap="large")
    with f1:
        network_hours = agg.hour_profile(by_time).loc[5:22]
        series = {}
        for c, color in zip(flagged, FLAGGED_MORE):
            series[short(c)] = (agg.hour_profile(by_time, c).loc[5:22] / network_hours, color, "solid")
        if series:
            profile(series, "Scheduled departure hour (local)", "× network average", reference=1.0, height=320,
                    label_lines=True)
    with f2:
        if first_wave_story:
            bt = {c: agg.band_table(by_time, c) for c in flagged}
            fw = {c: bt[c].loc["<09:00"] for c in flagged}
            widest = all(bt[c]["vs_network"].idxmax() == "<09:00" for c in flagged)
            always_worse = all((series[short(c)][0] > 1).all() for c in flagged)
            share_f = joined([f"{fw[c]['flights'] / bt[c]['flights'].sum():.0%}" for c in flagged])
            share_x = joined([f"{fw[c]['excess_hours_per_year'] / bt[c]['excess_hours_per_year'].sum():.0%}" for c in flagged])
            st.markdown(
                ("**Their biggest gap is before 09:00.** " if widest else "**They lose the most hours before 09:00.** ")
                + "Across all airlines, carrier-attributable delay is lowest in the late morning and builds through the "
                "day, and theirs follows the same shape. "
                + ("But they're worse than the network at every hour" if always_worse else "But")
                + (", and the gap is widest early: before 09:00" if widest else " before 09:00")
                + f" they run {joined([f'{fw[c]['vs_network']:.2f}×' for c in flagged])} the network rate.\n\n"
                f"Those early flights are {share_f} of their flights but {share_x} of their excess delay. And a late "
                "first departure carries on through the aircraft's day, as below."
            )
        else:
            st.markdown(
                f"**In {period} alone, the flagged airlines don't all lose the most time at the same time of day.** "
                "The chart shows how far each one runs above the network at every hour. Over both years together, "
                "SkyWest and American both lose the most before 09:00, which is what the recommendation is based on. "
                "Switch the period back to both years to see that."
            )
    st.markdown("**One aircraft's day**")
    st.image(rotation_diagram(), width="stretch")
    st.caption(ROTATION_CAPTION)

    st.html('<p class="finding-no">FINDING 03</p>')
    flagged_airports = airports.index[airports["flagged"]].tolist()
    st.subheader("Airports matter much less than airlines", anchor="f3")
    st.markdown(
        "**Fixing airlines is worth far more than fixing airports.** "
        f"{len(flagged_airports)} of {len(airports)} major airports are flagged "
        f"({', '.join(airport_cities().get(a, a).split(',')[0] for a in flagged_airports) or 'none'}), but together "
        f"they add about {round(airports.loc[flagged_airports, 'excess_hours_per_year'].sum(), -2):,.0f} excess "
        f"delay hours a year, against {round(carriers.loc[flagged, 'excess_hours_per_year'].sum(), -2):,.0f} for the "
        "flagged airlines. Click a dot to see who's behind an airport's delay."
    )
    airport_map("findings_map")
    st.caption("Bubble size = departures. Colour = carrier-attributable delay against the network (blue better, "
               "orange worse). Labelled = flagged. San Juan, Puerto Rico isn't on the map; pick it from the list "
               "on the Airports tab.")

    st.html('<p class="finding-no">SO WHAT</p>')
    st.subheader(f"Fixing their first flights of the day is worth about {round(first_wave, -2):,.0f} hours a year",
                 anchor="so-what")
    st.markdown(
        "**Start with the flights before 09:00.** If the flagged airlines' departures before 09:00 had the same "
        "carrier-attributable delay rate as all airlines at that time, that much delay would disappear a year, before "
        "counting the knock-on delay to later flights shown above. Likely places to look are overnight maintenance "
        "sign-off, crew turning up on time and getting aircraft ready (cleaning, catering, fuelling) at the airports "
        "where their first flights of the day leave from."
    )
    st.button("Try other fixes in the calculator →", on_click=run_recommendation, type="tertiary", key="so_what")

# ---- airlines -------------------------------------------------------------------------
with tab_airline:
    options = carriers.index.tolist()
    a1, a2 = st.columns(2)
    a1.selectbox("Airline", options, key="airline", format_func=carrier_label)
    code = st.session_state["airline"]
    a2.selectbox("Compare with (optional)", [None] + [c for c in options if c != code], key="compare",
                 format_func=lambda c: "None" if c is None else carrier_label(c), placeholder="None")
    compare = st.session_state["compare"]
    row = carriers.loc[code]
    name = short(code)

    st.markdown(
        f'<p class="lead">{name} averages <b>{row["min_per_flight"]:.1f} minutes</b> of carrier-attributable delay per '
        f"flight, {higher_lower(row['index'])} than the average across all airlines ({net:.1f} min). Compared with "
        f"other airlines at the same airports, it's {higher_lower(row['adj_index'])}."
        + (" <b>Flagged.</b>" if row["flagged"] else "") + "</p>",
        unsafe_allow_html=True,
    )
    m = st.columns(4)
    m[0].metric("Delay per flight", f"{row['min_per_flight']:.1f} min", f"{row['min_per_flight'] - net:+.1f} vs network",
                delta_color="inverse")
    m[1].metric("vs network", f"{row['index']:.2f}×", help="1.00× = exactly average")
    m[2].metric("vs others at same airports", f"{row['adj_index']:.2f}×",
                help="Compared with other airlines flying from the same airports")
    m[3].metric("Excess delay", f"{round(row['excess_hours_per_year'], -2):,.0f} h / yr",
                help="Delay hours a year above what the network average rate would give")
    year_cols = [c for c in carriers.columns if c.startswith("index_")]
    if len(year_cols) > 1:
        st.caption("By year: " + " · ".join(f"{c[-4:]}: {row[c]:.2f}× network" for c in year_cols))

    series_h = {name: (agg.hour_profile(by_time, code).loc[5:23], SELECTED, "solid")}
    series_d = {name: (agg.weekday_profile(by_time, code), SELECTED, "solid")}
    if compare:
        series_h[short(compare)] = (agg.hour_profile(by_time, compare).loc[5:23], COMPARE, "solid")
        series_d[short(compare)] = (agg.weekday_profile(by_time, compare), COMPARE, "solid")
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
    st.markdown(f"**Worst time of day: {BAND_WORDS[worst_band]}**, at {bands.loc[worst_band, 'vs_network']:.2f}× "
                "the network.")
    with st.expander("Show the numbers for each time of day"):
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
    worst3 = ", ".join(f"{a.split(' · ')[0].split(',')[0]} ({x:.1f}×)" for a, x in zip(station["Airport"].head(3), station["× others"].head(3)))
    st.markdown(f"**Where it's worst:** {worst3}, against other airlines at the same airport." if len(station)
                else "**Where it's worst:** not enough shared airports to compare.")
    with st.expander("Show the 10 airports with the biggest gap"):
        st.caption("Airports where both this airline and the other airlines have at least 2,000 departures.")
        st.dataframe(
            station, hide_index=True, width="stretch",
            column_config={
                "Departures": st.column_config.NumberColumn(format="localized"),
                "Min per flight": st.column_config.NumberColumn(format="%.1f"),
                "Others at airport": st.column_config.NumberColumn(format="%.1f"),
                "× others": st.column_config.NumberColumn(format="%.2f×"),
            },
        )

# ---- airports -------------------------------------------------------------------------
with tab_airport:
    st.selectbox("Airport", airports.index.tolist(), key="airport", format_func=airport_label,
                 help="Or click a dot on the map")
    code = st.session_state["airport"]
    row = airports.loc[code]
    city = airport_cities().get(code, code)
    here = by_airport[by_airport["origin"] == code].groupby("carrier")[["flights", "carrier_delay"]].sum()
    here["min_per_flight"] = here["carrier_delay"] / here["flights"]
    here["index"] = here["min_per_flight"] / net
    here = here.sort_values("min_per_flight", ascending=False)
    biggest = (here["carrier_delay"] / here["carrier_delay"].sum()).idxmax()
    sizable = here[here["flights"] >= 1_000 // (1 if n_years > 1 else 2)]
    worst_here = sizable["min_per_flight"].idxmax() if len(sizable) else biggest
    st.markdown(
        f'<p class="lead">Departures from {html.escape(city)} average <b>{row["min_per_flight"]:.1f} minutes</b> of '
        f"carrier-attributable delay, {higher_lower(row['index'])} than the average across all airports. "
        f"{html.escape(short(biggest))} accounts for the most of it "
        f"({here.loc[biggest, 'carrier_delay'] / here['carrier_delay'].sum():.0%} of the delay minutes here)"
        + (f"; {html.escape(short(worst_here))} has the highest rate ({here.loc[worst_here, 'min_per_flight']:.1f} min "
           "per departure)." if worst_here != biggest else ", and has the highest rate too.")
        + (" <b>Flagged.</b>" if row["flagged"] else "") + "</p>",
        unsafe_allow_html=True,
    )
    m = st.columns(3)
    m[0].metric("Delay per departure", f"{row['min_per_flight']:.1f} min")
    m[1].metric("vs network", f"{row['index']:.2f}×")
    m[2].metric("vs same airlines elsewhere", f"{row['adj_index']:.2f}×",
                help="Compared with the same airlines at other airports")
    airport_map("airport_map")
    st.caption("Click a dot to switch airport. Blue ring = selected; labelled = flagged.")
    bar_col, top_col = st.columns(2, gap="large")
    with bar_col:
        st.markdown(f"**Airlines at {html.escape(city.split(',')[0])}.** Click a bar to open that airline.")
        here_labels = [carrier_label(c) for c in here.index]
        hbar(here, here_labels, set(flagged), "min per departure", key="airport_airlines",
             on_select=lambda: pick_from_chart("airport_airlines", dict(zip(here_labels, here.index)), open_airline))
    with top_col:
        st.markdown("**Worst 15 major airports.** Click a bar to switch airport.")
        top = airports.head(15)
        top_labels = [airport_label(a) for a in top.index]
        hbar(top, top_labels, set(airports.index[airports["flagged"]]), "min per departure",
             selected=code, key="airport_chart",
             on_select=lambda: pick_from_chart("airport_chart", dict(zip(top_labels, top.index)), open_airport))

# ---- what if --------------------------------------------------------------------------
with tab_whatif:
    st.subheader("What would fixing it be worth?")
    st.markdown("Start from a preset, or pick airlines and departure times yourself, then slide how much of the gap "
                "to the network average they close.")
    st.pills("Presets", list(PRESETS), key="wi_preset", on_change=apply_preset)
    w1, w2 = st.columns(2)
    w1.multiselect("Airlines", carriers.index.tolist(), key="wi_airlines", format_func=carrier_label,
                   on_change=custom_preset)
    w2.multiselect("Scheduled departure", list(TIME_BANDS), key="wi_bands", on_change=custom_preset,
                   format_func=lambda b: BAND_WORDS[b].capitalize() if b in ("<09:00", "21+") else BAND_WORDS[b])
    st.slider("Share of the gap closed", 0, 100, step=10, format="%d%%", key="wi_close", on_change=custom_preset)
    picked, picked_bands = st.session_state["wi_airlines"], st.session_state["wi_bands"]
    close = st.session_state["wi_close"] / 100

    rows = []
    for c in picked:
        b = agg.band_table(by_time, c)
        sel = b.loc[picked_bands] if picked_bands else b.iloc[0:0]
        rows.append({
            "Airline": short(c),
            "vs all airlines": (sel["min_per_flight"] * sel["flights"]).sum()
            / (sel["network_min_per_flight"] * sel["flights"]).sum() if len(sel) else None,
            "Flights / yr": round(sel["flights"].sum() / n_years),
            "Hours saved / yr": agg.what_if(by_time, c, picked_bands, close),
        })
    total = sum(r["Hours saved / yr"] for r in rows)
    r1, r2 = st.columns([1, 2])
    r1.metric("Carrier-attributable delay removed", f"{round(total, -2):,.0f} hours a year")
    if total > 0:
        r2.markdown(
            f"That's about **{total / 365:,.0f} hours of delay every day**, or roughly "
            f"**{total * 60 / max(1, sum(r['Flights / yr'] for r in rows)):.1f} minutes** off each affected flight."
        )
    elif picked and picked_bands:
        r2.markdown("These airlines are already at or better than the network at those times, so there's nothing to "
                    "recover.")
    else:
        r2.markdown("Pick at least one airline and one departure time.")
    if rows:
        st.dataframe(
            pd.DataFrame(rows).round({"Hours saved / yr": 0}), hide_index=True, width="stretch",
            column_config={
                "vs all airlines": st.column_config.NumberColumn(format="%.2f×"),
                "Flights / yr": st.column_config.NumberColumn(format="localized"),
                "Hours saved / yr": st.column_config.NumberColumn(format="localized"),
            },
        )
    st.caption(
        "Conservative: a late early flight also delays the aircraft's later flights, which BTS books as "
        "late-arriving-aircraft delay and which isn't counted here. Airlines already better than the network at a "
        "given time count as zero."
    )

# ---- method & report ------------------------------------------------------------------
with tab_method:
    st.subheader("How the analysis works")
    st.markdown(
        '<p class="lead">The short version: one public dataset, one measure, and a deliberately strict rule for what '
        "counts as standing out. Everything on this tab describes the full 2024–2025 data.</p>",
        unsafe_allow_html=True,
    )
    d1, d2 = st.columns([3, 2], gap="large")
    with d1:
        st.markdown(
            "**The data.** The US Department of Transportation's Bureau of Transportation Statistics (BTS) records "
            "every domestic flight by the larger US airlines, with the cause of every delay of 15 minutes or more. "
            "This analysis uses January 2024 to December 2025: 14.1 million flights. Cancelled (199,000) and diverted (37,000) "
            "flights have no delay breakdown, so the measures use the 13.8 million completed flights. Only 2 delayed "
            "flights were missing their cause data.\n\n"
            "**Why US data.** CAAS/data.gov.sg only publishes aggregate monthly figures for Changi, and no flight-level, "
            "cause-coded delay data is publicly available. BTS is the best public dataset with that level of detail.\n\n"
            "**The measure.** Carrier-attributable delay minutes per completed flight. BTS splits each delay into five "
            "causes; *carrier* delay is the one inside the airline's control (maintenance, crew, cleaning, fuelling, "
            "baggage). BTS has no separate mechanical field, so this is never called mechanical delay here.\n\n"
            "**What counts as standing out.** An airline or airport is flagged only if it's at least 1.2× the network "
            "average on all three tests: over the two years, in each year separately, and against other airlines at "
            "the same airports (or, for an airport, the same airlines elsewhere). That last test stops anyone being "
            "penalised for flying from difficult airports. Airlines need 50,000+ flights and airports 20,000+ "
            "departures to be ranked.\n\n"
            "**Time of day** uses the *scheduled* departure hour, so a late flight doesn't move into a later hour."
        )
    with d2:
        st.markdown("**Checks**")
        st.markdown(
            "- Same result in **2024 and 2025 separately**: SkyWest and American are flagged in both, and each "
            "stays 1.30–1.37× the rate of other airlines at the same airports in each year.\n"
            "- With the **CrowdStrike IT outage** (19–28 July 2024) removed, SkyWest and American stay flagged. Frontier, "
            "just under the bar in 2024 (1.17×), also crosses it (1.22×), because the outage week pushed the "
            "network average up.\n"
            "- JetBlue looked bad in 2024 (1.54×) but not in 2025 (1.02×), so it isn't flagged."
        )
        st.markdown("**Limits**")
        st.markdown(
            "- Causes are only recorded for delays of 15+ minutes, and airlines report them themselves.\n"
            "- Carrier delay mixes maintenance with crew, cleaning and baggage; the data can't separate them.\n"
            "- Knock-on delay to later flights is recorded as late-arriving aircraft and isn't counted, so the "
            "savings figures are conservative.\n"
            "- SkyWest is a regional airline flying for United, Delta, American and Alaska; its numbers are its own "
            "operation's.\n"
            "- US domestic flying only; results may not carry over to other markets such as Changi."
        )
    st.divider()
    st.markdown("**The full report** has the method in detail, every supporting table and the robustness checks.")
    if REPORT_PDF.exists():
        st.download_button("Download the full report (PDF)", data=REPORT_PDF.read_bytes(),
                           file_name="where-airlines-lose-time-report.pdf", mime="application/pdf", type="primary")
    st.caption("Airport coordinates: OurAirports.")

st.divider()
st.caption(
    "Source: US DOT Bureau of Transportation Statistics, Reporting Carrier On-Time Performance. "
    "Cause minutes are only recorded for flights 15+ minutes late and are self-reported by airlines."
)
