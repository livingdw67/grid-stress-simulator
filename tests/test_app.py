"""Runs the Streamlit dashboard headlessly and checks it renders without errors."""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from grid_model import ALL_COUNTIES, GUIDE_BANDS

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


def test_dashboard_shows_the_statewide_total():
    at = AppTest.from_file(APP, default_timeout=60).run()
    at.sidebar.selectbox[0].set_value(ALL_COUNTIES).run()
    assert not at.exception
    assert any("All counties, South Carolina" in m.value for m in at.markdown)
    homes = at.metric[0]
    assert homes.label == "Homes in state"
    assert float(homes.value.replace(",", "")) == pytest.approx(2_190_000, rel=0.01)


def test_guide_bands_sit_inside_each_slider_and_around_its_default():
    at = AppTest.from_file(APP, default_timeout=60).run()
    for key, (lo, hi) in GUIDE_BANDS.items():
        slider = at.slider(key=key)
        assert slider.min <= lo < hi <= slider.max, key
        assert lo <= slider.value <= hi, key
