"""Runs the Streamlit dashboard headlessly and checks it renders without errors."""
from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parent.parent / "app.py")


def test_dashboard_renders_with_defaults():
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert not at.exception
    assert any("Greenville County" in m.value for m in at.markdown)
    assert len(at.metric) == 4


def test_dashboard_switches_to_managed_charging():
    at = AppTest.from_file(APP, default_timeout=60).run()
    at.sidebar.radio[1].set_value("Managed (off-peak, 11 PM-2 AM)").run()
    assert not at.exception
    peak_note = next(m.value for m in at.markdown if m.value.startswith("**New peak:**"))
    assert "AM" in peak_note
