"""Load model behind the dashboard: county names, EV charging curves, and stacked load.

Kept free of Streamlit so it can be tested and reused outside the app.
"""
import numpy as np
import pandas as pd

# ResStock reports energy per 15-minute interval (kWh). Average power over the
# interval (kW) = kWh / 0.25 h = kWh * 4.
INTERVALS_PER_HOUR = 4
SLOTS_PER_DAY = 24 * INTERVALS_PER_HOUR
FURNACE_EFFICIENCY = 0.80  # Share of fuel energy a typical gas/propane/oil furnace delivers as heat

SC_COUNTIES = {
    "001": "Abbeville", "003": "Aiken", "005": "Allendale", "007": "Anderson", "009": "Bamberg",
    "011": "Barnwell", "013": "Beaufort", "015": "Berkeley", "017": "Calhoun", "019": "Charleston",
    "021": "Cherokee", "023": "Chester", "025": "Chesterfield", "027": "Clarendon", "029": "Colleton",
    "031": "Darlington", "033": "Dillon", "035": "Dorchester", "037": "Edgefield", "039": "Fairfield",
    "041": "Florence", "043": "Georgetown", "045": "Greenville", "047": "Greenwood", "049": "Hampton",
    "051": "Horry", "053": "Jasper", "055": "Kershaw", "057": "Lancaster", "059": "Laurens",
    "061": "Lee", "063": "Lexington", "065": "McCormick", "067": "Marion", "069": "Marlboro",
    "071": "Newberry", "073": "Oconee", "075": "Orangeburg", "077": "Pickens", "079": "Richland",
    "081": "Saluda", "083": "Spartanburg", "085": "Sumter", "087": "Union", "089": "Williamsburg",
    "091": "York",
}
ALL_COUNTIES = "ALL"  # County code for the statewide total built by add_statewide()

# Guide bands drawn on the dashboard sliders: values a planner could reasonably expect by about 2035.
# Users can still slide past them. Arithmetic and sources are in the README ("Slider guide bands").
GUIDE_BANDS = {
    # Furnaces last 15-20 years, so 50-67% are replaced by 2035; 10-40% of those switching to a heat pump
    # gives 5-27% of fossil-heated homes
    "hp_rate": (5, 25),
    # ENERGY STAR cold-climate floor (1.75 at 5°F) up to a high-efficiency unit's seasonal COP (HSPF2 10 / 3.412)
    "cop": (1.8, 3.0),
    # EVs are ~1% of SC vehicles today; ~55% of vehicles are replaced by 2035, and EVs taking 4-20% of those
    # sales gives 3-12% of vehicles, or 5-19% of households at 1.6 vehicles per household
    "ev_rate": (5, 20),
    # FHWA 2023 average is 11,106 miles a year (30 a day); second cars drive less, rural commutes more
    "daily_miles": (25, 40),
    # Popular EVs are rated 0.28-0.33 kWh/mile; at 32°F to 20°F they keep 88-70% of their range
    "kwh_per_mile": (0.32, 0.47),
}


def county_name(gisjoin):
    if gisjoin == ALL_COUNTIES:
        return "All counties"
    # NHGIS GISJOIN codes look like 'G4500150': state 45, county 015
    return f"{SC_COUNTIES.get(gisjoin[4:7], gisjoin)} County"


def add_statewide(profiles):
    """Append statewide rows (county = ALL_COUNTIES): homes and energy summed over every county."""
    state = profiles.drop(columns="county").groupby("timestamp", as_index=False).sum()
    state["county"] = ALL_COUNTIES
    return pd.concat([profiles, state], ignore_index=True)


def ev_daily_profile_kw(daily_kwh, charger_kw, managed):
    """Expected charging load (kW) per EV for each 15-minute slot of the day.

    Unmanaged: drivers plug in when they get home (start times ~ normal around 6 PM).
    Managed: charging starts are staggered across an off-peak window (11 PM - 2 AM).
    """
    slots = np.arange(SLOTS_PER_DAY)
    hours = slots / INTERVALS_PER_HOUR
    if managed:
        start_prob = ((hours >= 23) | (hours < 2)).astype(float)
    else:
        dist = np.minimum(np.abs(hours - 18), 24 - np.abs(hours - 18))  # circular distance from 6 PM
        start_prob = np.exp(-0.5 * (dist / 1.5) ** 2)
    start_prob /= start_prob.sum()

    # Load from one EV that starts charging at slot 0
    charge_slots = daily_kwh / charger_kw * INTERVALS_PER_HOUR
    single = np.zeros(len(slots))
    full = int(charge_slots)
    single[:full] = charger_kw
    single[full % len(slots)] += charger_kw * (charge_slots - full)

    # Expected load = start-time distribution convolved (circularly) with one charging session
    return np.real(np.fft.ifft(np.fft.fft(start_prob) * np.fft.fft(single)))


def interval_slot(timestamps):
    """Slot of the day (0-95) for each timestamp.

    ResStock timestamps mark the END of each 15-minute interval, so 00:15 is slot 0
    and 00:00 is slot 95 (the last interval of the previous day).
    """
    return ((timestamps.dt.hour * 60 + timestamps.dt.minute) // 15 - 1) % SLOTS_PER_DAY


def stacked_load_mw(df, hp_rate, cop, ev_rate, daily_kwh, charger_kw, managed):
    """Current, heat pump and EV residential load (MW) for one county's rows.

    df needs timestamp, units, elec_kwh, gas_heat_kwh, propane_heat_kwh and oil_heat_kwh.
    hp_rate and ev_rate are percentages (0-100).
    """
    homes = df["units"].iloc[0]
    fossil_heat_kwh = df["gas_heat_kwh"] + df["propane_heat_kwh"] + df["oil_heat_kwh"]

    # kWh per interval * 4 = kW, / 1000 = MW
    baseline = df["elec_kwh"] * INTERVALS_PER_HOUR / 1000
    heat_pumps = fossil_heat_kwh * FURNACE_EFFICIENCY / cop * (hp_rate / 100) * INTERVALS_PER_HOUR / 1000

    num_evs = homes * ev_rate / 100
    ev_profile_kw = ev_daily_profile_kw(daily_kwh, charger_kw, managed)
    evs = pd.Series(ev_profile_kw[interval_slot(df["timestamp"]).to_numpy()] * num_evs / 1000, index=df.index)

    return pd.DataFrame({"baseline": baseline, "heat_pumps": heat_pumps, "evs": evs,
                         "total": baseline + heat_pumps + evs})
