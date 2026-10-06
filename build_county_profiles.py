import sys
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import s3fs

# --- CONFIGURATION ---
# NREL ResStock county-level aggregates: weighted totals for ALL homes in each county,
# one file per county and building type, 15-minute energy in kWh.
AGG_ROOT = (
    "oedi-data-lake/nrel-pds-building-stock/end-use-load-profiles-for-us-building-stock/"
    "2021/resstock_amy2018_release_1/timeseries_aggregates/by_county/state=SC"
)
WINDOW_START = "2018-01-01"
WINDOW_END = "2018-03-01"  # Jan-Feb 2018 (includes the Jan 16-19 cold snap)
OUTPUT_FILE = "sc_county_winter_profiles.parquet"

COLUMNS = {
    "timestamp": "timestamp",
    "units_represented": "units",
    "out.electricity.total.energy_consumption": "elec_kwh",
    "out.natural_gas.heating.energy_consumption": "gas_heat_kwh",
    "out.propane.heating.energy_consumption": "propane_heat_kwh",
    "out.fuel_oil.heating.energy_consumption": "oil_heat_kwh",
}


def load_file(fs, path):
    with fs.open(path) as f:
        df = pd.read_csv(f, usecols=list(COLUMNS))
    df = df.rename(columns=COLUMNS)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df[(df["timestamp"] >= WINDOW_START) & (df["timestamp"] < WINDOW_END)].copy()
    # File names look like 'g4500150-single-family_detached.csv'
    df["county"] = path.split("/")[-1].split("-")[0].upper()
    return df


def main():
    print("--- Building SC county winter load profiles from NREL ResStock ---")
    fs = s3fs.S3FileSystem(anon=True)
    files = fs.ls(AGG_ROOT)
    print(f"Found {len(files)} county/building-type files. Downloading...")

    with ThreadPoolExecutor(max_workers=8) as pool:
        frames = list(pool.map(lambda p: load_file(fs, p), files))

    # Sum building types (single-family, multi-family, mobile homes) into one county total
    df = pd.concat(frames).groupby(["county", "timestamp"], as_index=False).sum()
    if df.empty:
        print("❌ No data loaded.")
        sys.exit(1)

    df.to_parquet(OUTPUT_FILE, index=False)
    print(f"✅ Saved {OUTPUT_FILE}: {df['county'].nunique()} counties, {len(df):,} rows")


if __name__ == "__main__":
    main()
