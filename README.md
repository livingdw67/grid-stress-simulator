# IRA Grid Stress Simulator

**How much do Inflation Reduction Act incentives for heat pumps and electric vehicles raise winter peak load on South Carolina's grid?**

![Dashboard view](App_view.png)

## Why It Matters

The Inflation Reduction Act gives households tax credits and rebates for two big electrification moves: replacing gas, propane, and oil furnaces with electric heat pumps, and buying electric vehicles. Both cut emissions, and both shift energy use onto the electric grid.

Timing is the problem. Heat pumps work hardest on the coldest mornings, and unmanaged EV charging lands in the early evening when people get home. If adoption clusters in one area, local transformers and feeders can be pushed past their limits.

This tool lets a utility planner pick a county, set adoption rates for heat pumps and EVs, and see how the winter peak changes before the installs happen.

## Approach

1. **Current load (all homes):** NREL [ResStock](https://resstock.nrel.gov/) county aggregates give 15-minute electricity use for every home in each South Carolina county (single-family, multi-family, and mobile homes), from the AMY2018 release on NREL's public S3 data lake.
2. **Heat pumps:** For the chosen share of gas, propane, and oil-heated homes, fuel used for heating is converted to delivered heat (80% furnace efficiency), then to heat pump electricity using the selected efficiency (COP).
3. **EV charging:** Each EV needs `daily miles × kWh/mile` per day. Unmanaged charging starts when drivers get home (centered on 6 PM); managed charging is staggered across an 11 PM–2 AM off-peak window. The expected charging curve is applied to the chosen share of households.
4. **Peak impact:** The three loads are stacked over the January 16–19, 2018 cold snap (or all of January–February) to show the new peak and what drives it.

All loads are shown as average power in MW. ResStock reports energy per 15-minute interval, so kW = kWh × 4.

## Example Findings: Greenville County, January 2018 Cold Snap

With 20% heat pump adoption (COP 2.5) and 20% of households owning an EV (30 miles/day):

* **Baseline peak:** about 1,079 MW across roughly 201,000 homes, at 8 AM on January 18. About 74% of South Carolina homes already heat with electricity, so the winter morning peak is heating-driven.
* **Heat pumps** add about 67 MW at that peak, a 6.2% increase.
* **Unmanaged EV charging** adds almost nothing to the morning peak because it lands around 6 PM.
* **Off-peak timers backfire:** when every EV starts charging at 11 PM, a new midnight peak forms on cold nights, about 1,150 MW with 97 MW of EV load, higher than the original morning peak. Staggered or utility-managed charging matters more than a simple time-of-use window.

## Dashboard

* **Controls:** county, time window, heat pump adoption and efficiency, EV adoption, daily miles, winter kWh/mile, charger power, and managed vs. unmanaged charging
* **Headline metrics:** homes in the county, new heat pumps and EVs, new peak load, and percent increase in peak
* **Stacked load chart:** current load plus added heat pump and EV load
* **Peak breakdown:** when the new peak occurs and how much each source contributes
* **Housing stock by heating fuel** for the selected county

## Run It

```bash
git clone https://github.com/livingdw67/grid-stress-simulator.git
cd grid-stress-simulator
pip install -r requirements.txt

python build_county_profiles.py   # 1. Build county winter load profiles from NREL (optional: file is included)
python pull_resstock_data.py      # 2. Pull SC housing characteristics (optional: CSV is included)
streamlit run app.py              # 3. Launch the dashboard
```

The processed data files are committed, so you can go straight to step 3.

`analyze_single_home.py` is a standalone deep dive showing how one gas-heated home's load changes after switching to a heat pump (`grid_stress_test_chart.png`).

## Limitations and Next Steps

* **County as a proxy for a feeder.** True transformer-level analysis needs a utility's feeder and GIS data, and adoption tends to cluster on specific streets.
* **Fixed heat pump efficiency.** Real COP drops as temperatures fall. Next: temperature-dependent COP from the weather data behind ResStock.
* **Simplified EV behavior.** One EV per adopting household and a single arrival-time distribution. Next: NREL EVI-Pro charging profiles and workplace charging.
* **2018 weather and housing stock.** Results reflect the AMY2018 ResStock release, before recent heat pump and EV growth.

## Tech Stack

Python, pandas, NumPy, PyArrow, s3fs (NREL public S3), Streamlit, Plotly, Matplotlib, Seaborn
