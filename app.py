import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from grid_model import county_name, stacked_load_mw

# --- CONFIGURATION ---
st.set_page_config(page_title="IRA Grid Stress Simulator", layout="wide")


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
num_evs = homes * ev_rate / 100
loads = stacked_load_mw(df, hp_rate, cop, ev_rate, daily_miles * kwh_per_mile, charger_kw, managed)
baseline_mw, hp_mw, ev_mw, total_mw = loads["baseline"], loads["heat_pumps"], loads["evs"], loads["total"]
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
