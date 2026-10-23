import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from grid_model import ALL_COUNTIES, GUIDE_BANDS, add_statewide, county_name, stacked_load_mw

# --- CONFIGURATION ---
# Theme comes from .streamlit/config.toml (Daniel Livingston brand: navy, teal, one amber highlight)
st.set_page_config(page_title="IRA Grid Stress Simulator", page_icon="assets/favicon.png", layout="wide")


# --- 1. LOAD DATA ---
@st.cache_data
def load_data():
    try:
        profiles = pd.read_parquet("sc_county_winter_profiles.parquet")
    except FileNotFoundError:
        st.error("County profiles not found. Run 'build_county_profiles.py' first.")
        st.stop()
    profiles["timestamp"] = pd.to_datetime(profiles["timestamp"])
    profiles = add_statewide(profiles)

    try:
        meta = pd.read_csv("sc_resstock_metadata.csv")
    except FileNotFoundError:
        meta = pd.DataFrame()
    return profiles, meta


profiles, meta = load_data()

# --- 2. SIDEBAR CONTROLS ---
# Each guided slider gets its GUIDE_BANDS range drawn on the track: a shaded span between two lines,
# positioned as a percentage of the slider's full range
BAND_STYLE = ("content: ''; position: absolute; top: 50%; height: 14px; transform: translateY(-50%); "
              "box-sizing: border-box; border-left: 2px solid #9fb1c7; border-right: 2px solid #9fb1c7; "
              "background: rgba(127, 166, 209, 0.16); pointer-events: none;")
band_css = []


def guided_slider(label, key, min_value, max_value, value, step=None, unit="", why=""):
    lo, hi = GUIDE_BANDS[key]
    left, right = ((v - min_value) / (max_value - min_value) * 100 for v in (lo, hi))
    band_css.append(f".st-key-{key} [data-testid='stSlider'] [role='group'] > div::before "
                    f"{{{BAND_STYLE} left: calc({left:.2f}% - 1px); width: calc({right - left:.2f}% + 2px);}}")
    return st.sidebar.slider(label, min_value, max_value, value, step, key=key,
                             help=f"Guide band: {lo}-{hi}{unit}. {why}")


st.sidebar.title("Grid Stress Controls")
st.sidebar.caption("Lines on each slider mark a reasonable range for about 2035 (hover the ? for the reasoning). "
                   "The full slider is still available.")

counties = sorted(profiles["county"].unique(), key=lambda c: (c != ALL_COUNTIES, county_name(c)))
selected = st.sidebar.selectbox("County", counties, index=counties.index("G4500450") if "G4500450" in counties else 0,
                                format_func=county_name)

window = st.sidebar.radio("Time window", ["Cold snap (Jan 16-19, 2018)", "Full winter (Jan-Feb 2018)"])

st.sidebar.markdown("### Heat pumps")
hp_rate = guided_slider("Adoption (% of gas, propane, and oil-heated homes)", "hp_rate", 0, 100, 20, unit="%",
                        why="Furnaces last 15-20 years, so half to two-thirds are replaced by 2035. "
                            "The band assumes 10-40% of those replacements switch to a heat pump.")
cop = guided_slider("Heat pump efficiency (COP)", "cop", 1.5, 4.0, 2.5, 0.1,
                    why="Heat delivered per unit of electricity. Cold-climate heat pumps must still reach 1.75 at 5°F; "
                        "a high-efficiency unit averages about 3 over a season. Cold mornings sit near the low end.")

st.sidebar.markdown("### Electric vehicles")
ev_rate = guided_slider("Adoption (% of households with an EV)", "ev_rate", 0, 100, 20, unit="%",
                        why="About 1% of SC vehicles are EVs today. If EVs take 4-20% of new car sales until 2035, "
                            "when about half the fleet has been replaced, 5-19% of households would have one.")
daily_miles = guided_slider("Daily miles per EV", "daily_miles", 10, 80, 30, unit=" miles",
                            why="The average U.S. car is driven 11,106 miles a year, about 30 a day (FHWA, 2023). "
                                "Second cars drive less; rural commutes drive more.")
kwh_per_mile = guided_slider("EV energy use (kWh/mile, winter)", "kwh_per_mile", 0.25, 0.50, 0.35, 0.01,
                             unit=" kWh/mile",
                             why="Popular EVs are rated 0.28-0.33 kWh/mile. Between 32°F and 20°F they keep 70-88% "
                                 "of their range, so they need 14-43% more energy per mile (Recurrent, 2025).")
charger_kw = st.sidebar.select_slider("Home charger power (kW)", [1.4, 3.3, 7.2, 11.5], value=7.2)
managed = st.sidebar.radio("Charging behavior", ["Unmanaged (plug in on arrival)", "Managed (off-peak, 11 PM-2 AM)"]) != \
    "Unmanaged (plug in on arrival)"
st.sidebar.html(f"<style>{''.join(band_css)}</style>")

# --- 3. CALCULATIONS ---
df = profiles[profiles["county"] == selected].sort_values("timestamp").copy()
if window.startswith("Cold snap"):
    df = df[(df["timestamp"] > "2018-01-16") & (df["timestamp"] <= "2018-01-20")]

area = "state" if selected == ALL_COUNTIES else "county"
homes = df["units"].iloc[0]
num_evs = homes * ev_rate / 100
loads = stacked_load_mw(df, hp_rate, cop, ev_rate, daily_miles * kwh_per_mile, charger_kw, managed)
baseline_mw, hp_mw, ev_mw, total_mw = loads["baseline"], loads["heat_pumps"], loads["evs"], loads["total"]
old_peak, new_peak = baseline_mw.max(), total_mw.max()
peak_time = df.loc[total_mw.idxmax(), "timestamp"]

# --- 4. DASHBOARD ---
st.title("IRA Electrification Impact Simulator")
# The brand's short amber rule under the headline
st.markdown('<div style="width:56px;height:4px;background:#f0a742;border-radius:2px;margin:-0.5rem 0 1rem"></div>',
            unsafe_allow_html=True)
st.markdown(f"**{county_name(selected)}, South Carolina** · residential load from NREL ResStock (all homes in the {area})")

in_area = meta if selected == ALL_COUNTIES or meta.empty else meta[meta["in.county"] == selected]
fuel_shares = in_area["in.heating_fuel"].value_counts(normalize=True) if not meta.empty else pd.Series(dtype=float)
fossil_share = fuel_shares.drop("Electricity", errors="ignore").sum()
num_heat_pumps = homes * fossil_share * hp_rate / 100

c1, c2, c3, c4 = st.columns(4)
c1.metric(f"Homes in {area}", f"{homes:,.0f}")
c2.metric("New heat pumps / EVs", f"{num_heat_pumps:,.0f} / {num_evs:,.0f}")
c3.metric("Peak residential load (MW)", f"{new_peak:,.1f}", delta=f"+{new_peak - old_peak:,.1f} MW", delta_color="inverse")
c4.metric("Peak increase", f"{(new_peak / old_peak - 1) * 100:.1f}%" if old_peak > 0 else "n/a", delta_color="inverse")

st.subheader(window)
fig = go.Figure()
fig.add_trace(go.Scatter(x=df["timestamp"], y=baseline_mw, name="Current residential load",
                         stackgroup="load", line=dict(color="#5fc4c0", width=0.5), fillcolor="rgba(95, 196, 192, 0.55)"))
fig.add_trace(go.Scatter(x=df["timestamp"], y=hp_mw, name=f"Added: heat pumps ({hp_rate}% adoption)",
                         stackgroup="load", line=dict(color="#f0a742", width=0.5), fillcolor="rgba(240, 167, 66, 0.85)"))
fig.add_trace(go.Scatter(x=df["timestamp"], y=ev_mw, name=f"Added: EV charging ({ev_rate}% adoption)",
                         stackgroup="load", line=dict(color="#7fa6d1", width=0.5), fillcolor="rgba(127, 166, 209, 0.85)"))
fig.update_layout(height=500, hovermode="x unified", yaxis_title="Residential load (MW)",
                  xaxis_title="Time", legend=dict(y=1.12, orientation="h"),
                  paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(color="#9fb1c7"))
fig.update_xaxes(gridcolor="#2b3f58", linecolor="#2b3f58")
fig.update_yaxes(gridcolor="#2b3f58", linecolor="#2b3f58", zerolinecolor="#2b3f58")
st.plotly_chart(fig, width="stretch")

at_peak = df.index[total_mw.argmax()]
st.markdown(
    f"**New peak:** {peak_time:%a %b %d, %I:%M %p} · "
    f"current load {baseline_mw[at_peak]:,.1f} MW + heat pumps {hp_mw[at_peak]:,.1f} MW + EVs {ev_mw[at_peak]:,.1f} MW"
)

# --- 5. HOUSING STOCK ---
if not fuel_shares.empty:
    st.markdown("### Housing stock by heating fuel")
    st.caption(f"Shares from the ResStock sample for this {area}, scaled to the {area}'s total homes.")
    stock = pd.DataFrame({"Heating fuel": fuel_shares.index, "Share of homes": (fuel_shares.values * 100).round(1),
                          "Estimated homes": (fuel_shares.values * homes).round(-1).astype(int)})
    st.dataframe(stock, width="stretch", hide_index=True)
