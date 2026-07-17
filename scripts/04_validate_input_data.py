from pathlib import Path
import sys

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SIMULATED = ROOT / "data" / "simulated"
REFERENCE = ROOT / "data" / "reference"
TESTS = ROOT / "tests"
OUTPUT = TESTS / "input_data_validation_results.csv"

EXPECTED_MONTHS = {"2026-02", "2026-03", "2026-04", "2026-05"}
CONSUMPTION_COLUMNS = [
    "weekend_kwh",
    "peak_kwh",
    "shoulder_kwh",
    "off_peak_kwh",
    "super_off_peak_kwh",
]


def result(test_id: str, test_name: str, passed: bool, detail: str) -> dict:
    return {
        "test_id": test_id,
        "test_name": test_name,
        "test_status": "PASS" if passed else "FAIL",
        "detail": detail,
    }


def validate_inputs() -> pd.DataFrame:
    retailers = pd.read_csv(SIMULATED / "retailer_master.csv")
    icps = pd.read_csv(SIMULATED / "icp_master.csv")
    consumption = pd.read_csv(
        SIMULATED / "monthly_consumption.csv",
        parse_dates=["billing_period_start", "billing_period_end"],
    )
    price_2025 = pd.read_csv(REFERENCE / "price_schedule_2025.csv")
    price_2026 = pd.read_csv(REFERENCE / "price_schedule_2026.csv")
    valid_categories = set(price_2025["price_category_code"]) & set(
        price_2026["price_category_code"]
    )

    results = []
    results.append(result("I01", "Retailer count", len(retailers) == 5, f"Found {len(retailers)}"))
    results.append(result("I02", "ICP count", len(icps) == 500, f"Found {len(icps)}"))
    results.append(
        result(
            "I03",
            "Monthly consumption count",
            len(consumption) == 2000,
            f"Found {len(consumption)}",
        )
    )
    results.append(
        result(
            "I04",
            "Unique ICP identifiers",
            icps["icp_id"].is_unique,
            f"Duplicate ICP IDs: {icps['icp_id'].duplicated().sum()}",
        )
    )
    results.append(
        result(
            "I05",
            "Unique consumption identifiers",
            consumption["consumption_id"].is_unique,
            f"Duplicate consumption IDs: {consumption['consumption_id'].duplicated().sum()}",
        )
    )

    orphan_retailers = set(icps["retailer_id"]) - set(retailers["retailer_id"])
    results.append(
        result(
            "I06",
            "ICP retailer references",
            not orphan_retailers,
            f"Unknown retailer IDs: {sorted(orphan_retailers)}",
        )
    )
    orphan_icps = set(consumption["icp_id"]) - set(icps["icp_id"])
    results.append(
        result(
            "I07",
            "Consumption ICP references",
            not orphan_icps,
            f"Unknown ICP IDs: {len(orphan_icps)}",
        )
    )
    invalid_categories = set(icps["price_category_code"]) - valid_categories
    results.append(
        result(
            "I08",
            "Valid price categories",
            not invalid_categories,
            f"Invalid categories: {sorted(invalid_categories)}",
        )
    )

    category_mapping_count = (
        icps.groupby("price_category_code")[["connection_group", "control_type"]]
        .apply(lambda group: len(group.drop_duplicates()), include_groups=False)
        .gt(1)
        .sum()
    )
    results.append(
        result(
            "I09",
            "One business mapping per price category",
            category_mapping_count == 0,
            f"Categories with conflicting mappings: {category_mapping_count}",
        )
    )

    actual_months = set(consumption["billing_month"])
    results.append(
        result(
            "I10",
            "Expected billing months",
            actual_months == EXPECTED_MONTHS,
            f"Months: {sorted(actual_months)}",
        )
    )
    month_counts = consumption.groupby("icp_id")["billing_month"].nunique()
    results.append(
        result(
            "I11",
            "Four months per ICP",
            month_counts.eq(4).all(),
            f"ICPs without four months: {(~month_counts.eq(4)).sum()}",
        )
    )

    calculated_days = (
        consumption["billing_period_end"] - consumption["billing_period_start"]
    ).dt.days + 1
    results.append(
        result(
            "I12",
            "Billing-day calculation",
            calculated_days.eq(consumption["icp_days"]).all(),
            f"Incorrect day counts: {(~calculated_days.eq(consumption['icp_days'])).sum()}",
        )
    )
    results.append(
        result(
            "I13",
            "Non-negative consumption",
            consumption[CONSUMPTION_COLUMNS].ge(0).all().all(),
            f"Negative values: {consumption[CONSUMPTION_COLUMNS].lt(0).sum().sum()}",
        )
    )

    calculated_total = consumption[CONSUMPTION_COLUMNS].sum(axis=1).round(3)
    total_matches = calculated_total.eq(consumption["total_kwh"].round(3))
    results.append(
        result(
            "I14",
            "Time-band total reconciliation",
            total_matches.all(),
            f"Rows not reconciling: {(~total_matches).sum()}",
        )
    )

    simulated_origin_ok = (
        retailers["data_origin"].eq("Simulated").all()
        and icps["data_origin"].eq("Simulated").all()
        and consumption["data_origin"].eq("Simulated").all()
    )
    results.append(
        result(
            "I15",
            "Simulated-data labelling",
            simulated_origin_ok,
            "All generated datasets must be explicitly labelled Simulated",
        )
    )

    return pd.DataFrame(results)


def main() -> None:
    results = validate_inputs()
    TESTS.mkdir(parents=True, exist_ok=True)
    results.to_csv(OUTPUT, index=False)

    failed = results.loc[results["test_status"] == "FAIL"]
    print("INPUT DATA VALIDATION RESULTS")
    print(f"- tests run: {len(results)}")
    print(f"- passed: {(results['test_status'] == 'PASS').sum()}")
    print(f"- failed: {len(failed)}")

    if not failed.empty:
        for row in failed.itertuples(index=False):
            print(f"- {row.test_id} {row.test_name}: {row.detail}")
        sys.exit(1)


if __name__ == "__main__":
    main()
