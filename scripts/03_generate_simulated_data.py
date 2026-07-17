from calendar import monthrange
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "simulated"
RANDOM_SEED = 20260716
ICP_COUNT = 500

CATEGORY_CONFIG = {
    "URES": {
        "connection_group": "Residential Low User",
        "control_type": "Uncontrolled",
        "probability": 0.13,
        "base_monthly_kwh": 500,
        "tou_alpha": [6.0, 5.2, 5.6, 3.2, 1.0],
    },
    "RES": {
        "connection_group": "Residential Low User",
        "control_type": "Controlled",
        "probability": 0.64,
        "base_monthly_kwh": 540,
        "tou_alpha": [6.0, 4.6, 5.8, 3.8, 1.0],
    },
    "RSU": {
        "connection_group": "Residential Standard User",
        "control_type": "Uncontrolled",
        "probability": 0.05,
        "base_monthly_kwh": 760,
        "tou_alpha": [6.0, 5.4, 5.5, 3.1, 1.0],
    },
    "RSC": {
        "connection_group": "Residential Standard User",
        "control_type": "Controlled",
        "probability": 0.18,
        "base_monthly_kwh": 800,
        "tou_alpha": [6.0, 4.7, 5.7, 3.7, 1.0],
    },
}

MONTH_FACTORS = {
    "2026-02-01": 0.95,
    "2026-03-01": 1.00,
    "2026-04-01": 1.08,
    "2026-05-01": 1.18,
}


def generate_retailers() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "retailer_id": [f"RET{i:03d}" for i in range(1, 6)],
            "retailer_name": [f"Simulated Retailer {letter}" for letter in "ABCDE"],
            "billing_frequency": ["Monthly"] * 5,
            "active_flag": [True] * 5,
            "data_origin": ["Simulated"] * 5,
        }
    )


def generate_icps(rng: np.random.Generator, retailers: pd.DataFrame) -> pd.DataFrame:
    category_codes = list(CATEGORY_CONFIG)
    category_probabilities = [CATEGORY_CONFIG[code]["probability"] for code in category_codes]
    retailer_probabilities = [0.34, 0.25, 0.18, 0.14, 0.09]

    assigned_categories = rng.choice(
        category_codes, size=ICP_COUNT, p=category_probabilities
    )
    assigned_retailers = rng.choice(
        retailers["retailer_id"], size=ICP_COUNT, p=retailer_probabilities
    )
    region = rng.choice(
        ["Christchurch Urban", "Selwyn", "Central Canterbury Rural"],
        size=ICP_COUNT,
        p=[0.76, 0.16, 0.08],
    )

    start_offsets = rng.integers(0, 365 * 4, size=ICP_COUNT)
    connection_start = pd.Timestamp("2021-01-01") + pd.to_timedelta(start_offsets, unit="D")

    rows = []
    for index, category_code in enumerate(assigned_categories, start=1):
        config = CATEGORY_CONFIG[category_code]
        rows.append(
            {
                "icp_id": f"ICP{index:06d}",
                "retailer_id": assigned_retailers[index - 1],
                "connection_group": config["connection_group"],
                "control_type": config["control_type"],
                "price_category_code": category_code,
                "region": region[index - 1],
                "connection_start_date": connection_start[index - 1].date(),
                "connection_end_date": "",
                "status": "Active",
                "data_origin": "Simulated",
            }
        )
    return pd.DataFrame(rows)


def generate_consumption(
    rng: np.random.Generator, icps: pd.DataFrame
) -> pd.DataFrame:
    rows = []
    component_columns = [
        "weekend_kwh",
        "peak_kwh",
        "shoulder_kwh",
        "off_peak_kwh",
        "super_off_peak_kwh",
    ]

    for icp in icps.itertuples(index=False):
        config = CATEGORY_CONFIG[icp.price_category_code]
        for month_text, seasonal_factor in MONTH_FACTORS.items():
            period_start = pd.Timestamp(month_text)
            days_in_month = monthrange(period_start.year, period_start.month)[1]
            period_end = period_start + pd.offsets.MonthEnd(0)

            # A lognormal distribution creates realistic positive variation while
            # keeping the configured value close to the arithmetic mean.
            sigma = 0.28
            mean_parameter = np.log(config["base_monthly_kwh"] * seasonal_factor) - sigma**2 / 2
            monthly_total = float(rng.lognormal(mean=mean_parameter, sigma=sigma))

            shares = rng.dirichlet(config["tou_alpha"])
            component_values = np.round(monthly_total * shares, 3)
            total_kwh = round(float(component_values.sum()), 3)

            row = {
                "consumption_id": f"{icp.icp_id}-{period_start:%Y%m}",
                "icp_id": icp.icp_id,
                "billing_month": period_start.strftime("%Y-%m"),
                "billing_period_start": period_start.date(),
                "billing_period_end": period_end.date(),
                "icp_days": days_in_month,
                **dict(zip(component_columns, component_values)),
                "total_kwh": total_kwh,
                "data_origin": "Simulated",
            }
            rows.append(row)

    return pd.DataFrame(rows)


def main() -> None:
    rng = np.random.default_rng(RANDOM_SEED)
    retailers = generate_retailers()
    icps = generate_icps(rng, retailers)
    consumption = generate_consumption(rng, icps)

    OUTPUT.mkdir(parents=True, exist_ok=True)
    retailers.to_csv(OUTPUT / "retailer_master.csv", index=False)
    icps.to_csv(OUTPUT / "icp_master.csv", index=False)
    consumption.to_csv(OUTPUT / "monthly_consumption.csv", index=False)

    print("SIMULATED DATA GENERATION COMPLETE")
    print(f"- random seed: {RANDOM_SEED}")
    print(f"- retailers: {len(retailers):,}")
    print(f"- ICPs: {len(icps):,}")
    print(f"- monthly consumption records: {len(consumption):,}")
    print(f"- total simulated consumption: {consumption['total_kwh'].sum():,.3f} kWh")


if __name__ == "__main__":
    main()
