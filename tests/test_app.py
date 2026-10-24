"""Smoke tests: the Streamlit app renders, its controls work, and the defaults match the report."""

from pathlib import Path

import pytest

from aviation_delays import aggregates

APP = Path(__file__).resolve().parents[1] / "app" / "streamlit_app.py"
pytestmark = pytest.mark.skipif(not (aggregates.AGG_DIR / "by_time.csv").exists(), reason="app aggregates not built")


def run_app():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(APP), default_timeout=60).run()
    assert not at.exception
    return at


def metrics(at):
    return {m.label: m.value for m in at.metric}


def pull_stats(at):
    """The headline numbers on the Findings tab (custom HTML)."""
    import re

    bodies = [h.proto.body for h in at.get("html")]
    return [re.search(r'class="pull">([^<]+)<', b).group(1) for b in bodies if 'class="pull"' in b]


def test_defaults_match_report():
    at = run_app()
    assert at.title[0].value == "Where airlines lose time"
    assert pull_stats(at) == ["5.2 min", "2 airlines", "20,600 h"]
    assert metrics(at)["Carrier-attributable delay removed"] == "20,600 hours a year"
    board = next(h.proto.body for h in at.get("html") if "DEPARTURES" in h.proto.body)
    assert board.count("FLAGGED") == 2 and "SKYWEST" in board
    assert at.session_state["airline"] == "OO"  # worst airline is preselected


def test_quick_start_buttons_open_the_right_tab():
    at = run_app()
    labels = [b.label for b in at.button]
    at.button[[i for i, label in enumerate(labels) if "worst airline" in label][0]].click().run()
    assert at.session_state["tab"] == "Airlines" and at.session_state["airline"] == "OO"

    at.button[[i for i, label in enumerate(labels) if "going wrong" in label][0]].click().run()
    assert at.session_state["tab"] == "Airports" and at.session_state["airport"] == "DTW"

    at.button[[i for i, label in enumerate(labels) if "fixing it be worth" in label][0]].click().run()
    assert at.session_state["tab"] == "What if"
    assert metrics(at)["Carrier-attributable delay removed"] == "20,600 hours a year"
    assert not at.exception


def test_what_if_presets_and_slider():
    at = run_app()
    at.slider(key="wi_close").set_value(50).run()
    assert metrics(at)["Carrier-attributable delay removed"] == "10,300 hours a year"
    assert at.session_state["wi_preset"] is None  # moving a control leaves the preset

    at.session_state["wi_preset"] = "Report recommendation"
    at.run()
    at.slider(key="wi_close").set_value(100).run()
    assert metrics(at)["Carrier-attributable delay removed"] == "20,600 hours a year"
    assert not at.exception


def test_compare_year_and_airport_controls():
    at = run_app()
    at.selectbox(key="compare").set_value("WN").run()
    at.selectbox(key="airport").set_value("ATL").run()
    assert not at.exception
    for year in ("2024", "2025"):
        at.session_state["year"] = year
        at.run()
        assert not at.exception
    at.session_state["year"] = "Both years"
    at.run()
    assert pull_stats(at)[1] == "2 airlines"
