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


def test_defaults_match_report():
    at = run_app()
    assert at.title[0].value == "✈️ Where airlines lose time"
    values = metrics(at)
    assert values["Airlines flagged"] == "2"
    assert values["First-wave fix (flagged airlines)"] == "20,600 h / yr"
    assert values["Carrier-attributable delay removed"] == "20,600 hours a year"
    assert at.session_state["airline"] == "OO"  # worst airline is preselected


def test_quick_start_buttons_open_the_right_tab():
    at = run_app()
    labels = [b.label for b in at.button]
    at.button[[i for i, label in enumerate(labels) if "worst airline" in label][0]].click().run()
    assert at.session_state["tab"] == "Airline explorer" and at.session_state["airline"] == "OO"

    at.button[[i for i, label in enumerate(labels) if "going wrong" in label][0]].click().run()
    assert at.session_state["tab"] == "Airport explorer" and at.session_state["airport"] == "DTW"

    at.button[[i for i, label in enumerate(labels) if "fix be worth" in label][0]].click().run()
    assert at.session_state["tab"] == "What-if calculator"
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
    assert metrics(at)["Airlines flagged"] == "2"
