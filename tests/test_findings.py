"""Checks that the README's Greenville County findings still hold on the committed data.

Scenario from the README: January 16-19, 2018 cold snap, 20% heat pump adoption at COP 2.5,
20% of households with an EV driving 30 miles a day at 0.35 kWh/mile on a 7.2 kW charger
(the dashboard defaults).
"""
from pathlib import Path

import pandas as pd
import pytest

from grid_model import stacked_load_mw

DATA = Path(__file__).resolve().parent.parent / "sc_county_winter_profiles.parquet"
GREENVILLE = "G4500450"
SCENARIO = dict(hp_rate=20, cop=2.5, ev_rate=20, daily_kwh=30 * 0.35, charger_kw=7.2)


@pytest.fixture(scope="module")
def cold_snap():
    profiles = pd.read_parquet(DATA)
    profiles["timestamp"] = pd.to_datetime(profiles["timestamp"])
    df = profiles[profiles["county"] == GREENVILLE].sort_values("timestamp")
    return df[(df["timestamp"] > "2018-01-16") & (df["timestamp"] <= "2018-01-20")]


def test_baseline_morning_peak(cold_snap):
    loads = stacked_load_mw(cold_snap, managed=False, **SCENARIO)
    peak_at = cold_snap.loc[loads["baseline"].idxmax(), "timestamp"]

    assert cold_snap["units"].iloc[0] == pytest.approx(201_000, rel=0.01)
    assert loads["baseline"].max() == pytest.approx(1_079, rel=0.01)
    assert (peak_at.month, peak_at.day) == (1, 18)
    assert 7 <= peak_at.hour <= 9


def test_heat_pumps_add_about_six_percent_at_the_morning_peak(cold_snap):
    loads = stacked_load_mw(cold_snap, managed=False, **SCENARIO)
    at_peak = loads["baseline"].idxmax()

    assert loads.loc[at_peak, "heat_pumps"] == pytest.approx(67, rel=0.03)
    assert loads.loc[at_peak, "heat_pumps"] / loads.loc[at_peak, "baseline"] == pytest.approx(0.062, abs=0.002)


def test_unmanaged_charging_barely_touches_the_morning_peak(cold_snap):
    loads = stacked_load_mw(cold_snap, managed=False, **SCENARIO)
    assert loads.loc[loads["baseline"].idxmax(), "evs"] < 1  # MW


def test_off_peak_timers_create_a_new_midnight_peak(cold_snap):
    loads = stacked_load_mw(cold_snap, managed=True, **SCENARIO)
    peak = loads["total"].idxmax()
    peak_at = cold_snap.loc[peak, "timestamp"]

    assert peak_at.hour >= 23 or peak_at.hour < 3
    assert loads.loc[peak, "total"] == pytest.approx(1_150, rel=0.01)
    assert loads.loc[peak, "evs"] == pytest.approx(97, rel=0.03)
    assert loads.loc[peak, "total"] > loads["baseline"].max()
