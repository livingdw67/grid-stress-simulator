"""Unit tests for the load model on synthetic inputs (no data files needed)."""
import numpy as np
import pandas as pd
import pytest

from grid_model import (ALL_COUNTIES, INTERVALS_PER_HOUR, SLOTS_PER_DAY, add_statewide, county_name,
                        ev_daily_profile_kw, interval_slot, stacked_load_mw)

HOURS = np.arange(SLOTS_PER_DAY) / INTERVALS_PER_HOUR


@pytest.mark.parametrize("managed", [False, True])
@pytest.mark.parametrize("daily_kwh, charger_kw", [(10.5, 7.2), (3.5, 1.4), (28.0, 11.5), (7.0, 3.3)])
def test_ev_profile_delivers_exactly_the_daily_energy(daily_kwh, charger_kw, managed):
    profile = ev_daily_profile_kw(daily_kwh, charger_kw, managed)
    assert profile.sum() / INTERVALS_PER_HOUR == pytest.approx(daily_kwh)


@pytest.mark.parametrize("managed", [False, True])
def test_ev_profile_stays_between_zero_and_charger_power(managed):
    profile = ev_daily_profile_kw(daily_kwh=28.0, charger_kw=7.2, managed=managed)
    assert profile.min() >= -1e-9
    assert profile.max() <= 7.2 + 1e-9


def test_managed_charging_only_runs_overnight():
    # 10.5 kWh at 7.2 kW takes about 1.5 hours, and starts fall between 11 PM and 2 AM,
    # so nothing should be charging from 4 AM to 11 PM.
    profile = ev_daily_profile_kw(daily_kwh=10.5, charger_kw=7.2, managed=True)
    daytime = (HOURS >= 4) & (HOURS < 23)
    assert profile[daytime].max() == pytest.approx(0, abs=1e-9)
    assert profile[~daytime].sum() > 0


def test_unmanaged_charging_peaks_in_the_early_evening():
    profile = ev_daily_profile_kw(daily_kwh=10.5, charger_kw=7.2, managed=False)
    assert 17 <= HOURS[profile.argmax()] <= 20
    assert profile[(HOURS >= 6) & (HOURS < 9)].max() < 0.01 * profile.max()


def test_interval_slot_treats_timestamps_as_interval_ends():
    ts = pd.Series(pd.to_datetime(["2018-01-18 00:15", "2018-01-18 00:30", "2018-01-18 23:45", "2018-01-19 00:00"]))
    assert interval_slot(ts).tolist() == [0, 1, 94, 95]


def test_county_name():
    assert county_name("G4500450") == "Greenville County"
    assert county_name("G4500010") == "Abbeville County"
    assert county_name("G4509990") == "G4509990 County"
    assert county_name(ALL_COUNTIES) == "All counties"


def synthetic_county(days=2, homes=1000, seed=0):
    ts = pd.date_range("2018-01-16 00:15", periods=days * SLOTS_PER_DAY, freq="15min")
    rng = np.random.default_rng(seed)
    return pd.DataFrame({
        "timestamp": ts,
        "units": homes,
        "elec_kwh": rng.uniform(200, 400, len(ts)),
        "gas_heat_kwh": rng.uniform(50, 150, len(ts)),
        "propane_heat_kwh": rng.uniform(0, 20, len(ts)),
        "oil_heat_kwh": rng.uniform(0, 5, len(ts)),
    })


def test_zero_adoption_leaves_the_baseline_unchanged():
    df = synthetic_county()
    loads = stacked_load_mw(df, hp_rate=0, cop=2.5, ev_rate=0, daily_kwh=10.5, charger_kw=7.2, managed=False)
    assert (loads["heat_pumps"] == 0).all()
    assert (loads["evs"] == 0).all()
    pd.testing.assert_series_equal(loads["total"], loads["baseline"], check_names=False)
    assert loads["baseline"].iloc[0] == pytest.approx(df["elec_kwh"].iloc[0] * 4 / 1000)


def test_total_is_the_sum_of_its_parts():
    loads = stacked_load_mw(synthetic_county(), hp_rate=30, cop=2.5, ev_rate=25, daily_kwh=10.5,
                            charger_kw=7.2, managed=True)
    np.testing.assert_allclose(loads["total"], loads[["baseline", "heat_pumps", "evs"]].sum(axis=1))


def test_heat_pump_load_scales_with_adoption_and_inversely_with_cop():
    df = synthetic_county()
    base = stacked_load_mw(df, 20, 2.5, 0, 10.5, 7.2, False)["heat_pumps"]
    np.testing.assert_allclose(stacked_load_mw(df, 40, 2.5, 0, 10.5, 7.2, False)["heat_pumps"], 2 * base)
    np.testing.assert_allclose(stacked_load_mw(df, 20, 5.0, 0, 10.5, 7.2, False)["heat_pumps"], base / 2)

    # One interval by hand: fuel energy * 80% furnace efficiency / COP * share, as MW
    fuel = df[["gas_heat_kwh", "propane_heat_kwh", "oil_heat_kwh"]].iloc[0].sum()
    assert base.iloc[0] == pytest.approx(fuel * 0.8 / 2.5 * 0.2 * 4 / 1000)


@pytest.mark.parametrize("managed", [False, True])
def test_ev_energy_over_whole_days_matches_fleet_demand(managed):
    days, homes = 3, 1000
    loads = stacked_load_mw(synthetic_county(days, homes), hp_rate=0, cop=2.5, ev_rate=20, daily_kwh=10.5,
                            charger_kw=7.2, managed=managed)
    fleet_mwh = loads["evs"].sum() / INTERVALS_PER_HOUR
    assert fleet_mwh == pytest.approx(days * homes * 0.20 * 10.5 / 1000)


def test_statewide_rows_sum_every_county():
    a = synthetic_county(homes=1000, seed=1).assign(county="G4500010")
    b = synthetic_county(homes=500, seed=2).assign(county="G4500030")
    profiles = add_statewide(pd.concat([a, b], ignore_index=True))
    state = profiles[profiles["county"] == ALL_COUNTIES].reset_index(drop=True)

    assert len(profiles) == 3 * len(a)
    assert (state["units"] == 1500).all()
    np.testing.assert_allclose(state["elec_kwh"], a["elec_kwh"] + b["elec_kwh"])

    # The model is linear in homes and energy, so the statewide load equals the sum of the county loads
    args = dict(hp_rate=20, cop=2.5, ev_rate=20, daily_kwh=10.5, charger_kw=7.2, managed=True)
    county_total = stacked_load_mw(a, **args)["total"].to_numpy() + stacked_load_mw(b, **args)["total"].to_numpy()
    np.testing.assert_allclose(stacked_load_mw(state, **args)["total"], county_total)
