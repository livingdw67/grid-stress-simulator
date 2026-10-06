import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# --- CONFIGURATION ---
st.set_page_config(page_title="IRA Grid Stress Simulator", layout="wide")

# ResStock reports energy per 15-minute interval (kWh). Average power over the
# interval (kW) = kWh / 0.25 h = kWh * 4.
INTERVALS_PER_HOUR = 4
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


def county_name(gisjoin):
    # NHGIS GISJOIN codes look like 'G4500150': state 45, county 015
    return f"{SC_COUNTIES.get(gisjoin[4:7], gisjoin)} County"


# --- 1. LOAD DATA ---
@st.cache_data
def load_data():
    try:
        profiles = pd.read_parquet("sc_county_winter_profiles.parquet")
    except FileNotFoundError:
        st.error("⚠️ County profiles not found. Run 'build_county_profiles.py' first.")
        st.stop()
    profiles["timestamp"] = pd.to_datetime(profiles["timestamp"])

    try:
        meta = pd.read_csv("sc_resstock_metadata.csv")
    except FileNotFoundError:
        meta = pd.DataFrame()
    return profiles, meta


def ev_daily_profile_kw(daily_kwh, charger_kw, managed):
    """Expected charging load (kW) per EV for each 15-minute slot of the day.

    Unmanaged: drivers plug in when they get home (start times ~ normal around 6 PM).
    Managed: charging starts are staggered across an off-peak window (11 PM - 2 AM).
    """
    slots = np.arange(24 * INTERVALS_PER_HOUR)
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


profiles, meta = load_data()

# --- 2. SIDEBAR CONTROLS ---
st.sidebar.title("Grid Stress Controls")

counties = sorted(profiles["county"].unique(), key=county_name)
selected = st.sidebar.selectbox("County", counties, index=counties.index("G4500450") if "G4500450" in counties else 0,
                                format_func=county_name)

window = st.sidebar.radio("Time window", ["Cold snap (Jan 16-19, 2018)", "Full winter (Jan-Feb 2018)"])

st.sidebar.markdown("### Heat pumps")
hp_rate = st.sidebar.slider("Adoption (% of gas, propane, and oil-heated homes)", 0, 100, 20)
cop = st.sidebar.slider("Heat pump efficiency (COP)", 1.5, 4.0, 2.5, 0.1,
                        help="Heat delivered per unit of electricity. Real heat pumps drop toward 2 or below in freezing weather.")

st.sidebar.markdown("### Electric vehicles")
ev_rate = st.sidebar.slider("Adoption (% of households with an EV)", 0, 100, 20)
daily_miles = st.sidebar.slider("Daily miles per EV", 10, 80, 30)
kwh_per_mile = st.sidebar.slider("EV energy use (kWh/mile, winter)", 0.25, 0.50, 0.35, 0.01)
charger_kw = st.sidebar.select_slider("Home charger power (kW)", [1.4, 3.3, 7.2, 11.5], value=7.2)
managed = st.sidebar.radio("Charging behavior", ["Unmanaged (plug in on arrival)", "Managed (off-peak, 11 PM-2 AM)"]) != \
    "Unmanaged (plug in on arrival)"

# --- 3. CALCULATIONS ---
df = profiles[profiles["county"] == selected].sort_values("timestamp").copy()
if window.startswith("Cold snap"):
    df = df[(df["timestamp"] > "2018-01-16") & (df["timestamp"] <= "2018-01-20")]

homes = df["units"].iloc[0]
fossil_heat_kwh = df["gas_heat_kwh"] + df["propane_heat_kwh"] + df["oil_heat_kwh"]

# All loads in MW (kWh per interval * 4 = kW, / 1000 = MW)
baseline_mw = df["elec_kwh"] * INTERVALS_PER_HOUR / 1000
hp_mw = fossil_heat_kwh * FURNACE_EFFICIENCY / cop * (hp_rate / 100) * INTERVALS_PER_HOUR / 1000

num_evs = homes * ev_rate / 100
ev_profile_kw = ev_daily_profile_kw(daily_miles * kwh_per_mile, charger_kw, managed)
# Timestamps mark the END of each 15-minute interval, so 00:15 is slot 0
slot = ((df["timestamp"].dt.hour * 60 + df["timestamp"].dt.minute) // 15 - 1) % len(ev_profile_kw)
ev_mw = pd.Series(ev_profile_kw[slot.to_numpy()] * num_evs / 1000, index=df.index)

total_mw = baseline_mw + hp_mw + ev_mw
old_peak, new_peak = baseline_mw.max(), total_mw.max()
peak_time = df.loc[total_mw.idxmax(), "timestamp"]

# --- 4. DASHBOARD ---
st.title("IRA Electrification Impact Simulator")
st.markdown(f"**{county_name(selected)}, South Carolina** · residential load from NREL ResStock (all homes in the county)")

fuel_shares = (meta.loc[meta["in.county"] == selected, "in.heating_fuel"].value_counts(normalize=True)
               if not meta.empty else pd.Series(dtype=float))
fossil_share = fuel_shares.drop("Electricity", errors="ignore").sum()
num_heat_pumps = homes * fossil_share * hp_rate / 100

c1, c2, c3, c4 = st.columns(4)
c1.metric("Homes in county", f"{homes:,.0f}")
c2.metric("New heat pumps / EVs", f"{num_heat_pumps:,.0f} / {num_evs:,.0f}")
c3.metric("Peak residential load (MW)", f"{new_peak:,.1f}", delta=f"+{new_peak - old_peak:,.1f} MW", delta_color="inverse")
c4.metric("Peak increase", f"{(new_peak / old_peak - 1) * 100:.1f}%" if old_peak > 0 else "n/a", delta_color="inverse")

st.subheader(window)
fig = go.Figure()
fig.add_trace(go.Scatter(x=df["timestamp"], y=baseline_mw, name="Current residential load",
                         stackgroup="load", line=dict(color="#1f77b4", width=0.5)))
fig.add_trace(go.Scatter(x=df["timestamp"], y=hp_mw, name=f"Added: heat pumps ({hp_rate}% adoption)",
                         stackgroup="load", line=dict(color="#d62728", width=0.5)))
fig.add_trace(go.Scatter(x=df["timestamp"], y=ev_mw, name=f"Added: EV charging ({ev_rate}% adoption)",
                         stackgroup="load", line=dict(color="#ff7f0e", width=0.5)))
fig.update_layout(height=500, hovermode="x unified", yaxis_title="Residential load (MW)",
                  xaxis_title="Time", legend=dict(y=1.12, orientation="h"))
st.plotly_chart(fig, width="stretch")

at_peak = df.index[total_mw.argmax()]
st.markdown(
    f"**New peak:** {peak_time:%a %b %d, %I:%M %p} · "
    f"current load {baseline_mw[at_peak]:,.1f} MW + heat pumps {hp_mw[at_peak]:,.1f} MW + EVs {ev_mw[at_peak]:,.1f} MW"
)

# --- 5. HOUSING STOCK ---
if not fuel_shares.empty:
    st.markdown("### Housing stock by heating fuel")
    st.caption("Shares from the ResStock sample for this county, scaled to the county's total homes.")
    stock = pd.DataFrame({"Heating fuel": fuel_shares.index, "Share of homes": (fuel_shares.values * 100).round(1),
                          "Estimated homes": (fuel_shares.values * homes).round(-1).astype(int)})
    st.dataframe(stock, width="stretch", hide_index=True)
