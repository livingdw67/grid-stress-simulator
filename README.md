# IRA Grid Stress Simulator

**Predicting Utility Vulnerabilities under the Inflation Reduction Act**

> *"A return to my roots: having statistically rigorous solutions ready for the next impending legislative doom."*

## Context & Mission
I'm a **Data Science Consultant** based in **Greer, SC**, with over 10 years of experience in the **Finance and Energy sectors**.

This project helps utilities prepare for the **Inflation Reduction Act**. It demonstrates grid vulnerabilities that arise when EV adoption spikes in concentrated areas—specifically if too many people utilize the tax credit to buy EVs in the same neighborhood.

## Key Features

* **Grid Stress Testing:** Simulates high-load scenarios on local transformers based on EV adoption rates.
* **Housing Archetype Analysis:** Uses `archetype_profile.csv` to model different home energy profiles (single-family, older construction, etc.).
* **ResStock Data Integration:** Ingests NREL ResStock data to create statistically accurate baselines for residential energy usage.
* **Visualization Dashboard:** Includes an `app.py` (Streamlit/Web) interface to visualize stress points dynamically.

## Installation

1.  **Clone the repository:**
    ```bash
    git clone [https://github.com/livingdw67/grid-stress-simulator.git](https://github.com/livingdw67/grid-stress-simulator.git)
    cd grid-stress-simulator
    ```

2.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

## Usage

1.  **Run the Dashboard:**
    Launch the interactive tool to see the data visually.
    ```bash
    streamlit run app.py
    ```

2.  **Run a Single Home Analysis:**
    To process specific housing profiles:
    ```bash
    python analyze_single_home.py
    ```

---
*Created by Daniel Livingston | Data Science Consultant*
