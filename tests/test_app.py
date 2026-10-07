"""Smoke test: the Streamlit app renders and the what-if calculator reproduces the report."""

from pathlib import Path

import pytest

from aviation_delays import aggregates

APP = Path(__file__).resolve().parents[1] / "app" / "streamlit_app.py"
pytestmark = pytest.mark.skipif(not (aggregates.AGG_DIR / "by_time.csv").exists(), reason="app aggregates not built")


def test_app_runs_and_defaults_match_report():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(APP), default_timeout=60).run()
    assert not at.exception
    assert at.title[0].value == "Where airlines lose time"
    values = {m.label: m.value for m in at.metric}
    assert values["Airlines flagged"] == "2"
    assert values["First-wave fix (flagged airlines)"] == "20,600 h / yr"
    assert values["Carrier-attributable delay removed"] == "20,600 hours a year"


def test_what_if_responds_to_inputs():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(APP), default_timeout=60).run()
    at.slider[0].set_value(50).run()
    assert not at.exception
    assert {m.label: m.value for m in at.metric}["Carrier-attributable delay removed"] == "10,300 hours a year"
    # switch the airline explorer to another carrier and the airport explorer to another airport
    at.selectbox[0].set_value("WN").run()
    at.selectbox[1].set_value("DTW").run()
    assert not at.exception
