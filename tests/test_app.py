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

    at.session_state["wi_preset"] = "The recommendation"
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


def test_single_year_notice_and_back_button():
    at = run_app()
    assert not [b for b in at.button if b.label == "Back to both years"]
    at.session_state["year"] = "2025"
    at.run()
    assert any("2025 only" in i.value for i in at.info)
    next(b for b in at.button if b.label == "Back to both years").click().run()
    assert at.session_state["year"] == "Both years" and not at.exception


def test_method_tab_offers_the_pdf_and_no_code_links():
    at = run_app()
    downloads = at.get("download_button")
    assert len(downloads) == 1 and "full report" in downloads[0].proto.label
    text = " ".join(m.value for m in at.markdown) + " ".join(c.value for c in at.caption)
    assert "github.com" not in text.lower()


def test_appearance_switch_writes_the_theme_and_reloads():
    at = run_app()
    assert at.session_state["appearance"] == "Light"  # test runner has no device theme: shows light
    assert not any("stActiveTheme" in h.proto.body for h in at.get("html"))
    at.session_state["appearance"] = "Dark"
    at.session_state["apply_appearance"] = "Dark"  # what the switch's on_change callback sets
    at.run()
    script = next(h.proto.body for h in at.get("html") if "stActiveTheme" in h.proto.body)
    assert '"Dark"' in script and 'searchParams.set("theme", "dark")' in script
    at.run()  # the request is used once, not on every rerun
    assert not any("stActiveTheme" in h.proto.body for h in at.get("html"))


def test_no_author_name_or_tool_credits_on_the_site():
    at = run_app()
    text = " ".join(m.value for m in at.markdown) + " ".join(c.value for c in at.caption)
    text += " ".join(h.proto.body for h in at.get("html"))
    assert "edwin" not in text.lower() and "built by" not in text.lower() and "built with" not in text.lower()


def test_site_text_is_neutral_not_first_person():
    import re

    at = run_app()
    text = " ".join(m.value for m in at.markdown) + " ".join(c.value for c in at.caption)
    text += " ".join(re.sub(r"<[^>]+>", " ", h.proto.body) for h in at.get("html")) + " ".join(s.value for s in at.subheader)
    assert not re.search(r"\b(I|I've|I'm|my|me)\b", text), re.search(r".{40}\b(I|I've|I'm|my|me)\b.{40}", text)
