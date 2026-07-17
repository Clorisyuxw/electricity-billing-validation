from pathlib import Path
import sys

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "data" / "reference"
SIMULATED = ROOT / "data" / "simulated"
OUTPUT = ROOT / "data" / "output"
TESTS = ROOT / "tests"

DETAIL_OUTPUT = OUTPUT / "expected_billing_detail.csv"
SUMMARY_OUTPUT = OUTPUT / "expected_billing_summary.csv"
TEST_OUTPUT = TESTS / "expected_billing_validation_results.csv"

# Each consumption column must map to exactly one official price component.
# Keeping this mapping in one place makes the calculation easy to inspect.
VARIABLE_COMPONENT_MAP = {
    "weekend_kwh": "Weekend",
    "peak_kwh": "Peak",
    "shoulder_kwh": "Shoulder",
    "off_peak_kwh": "Off Peak",
    "super_off_peak_kwh": "Super Off Peak",
}


def load_inputs() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Load master, consumption and official price data with date types."""
    icps = pd.read_csv(SIMULATED / "icp_master.csv")
    consumption = pd.read_csv(
        SIMULATED / "monthly_consumption.csv",
        parse_dates=["billing_period_start", "billing_period_end"],
    )
    prices = pd.concat(
        [
            pd.read_csv(REFERENCE / "price_schedule_2025.csv"),
            pd.read_csv(REFERENCE / "price_schedule_2026.csv"),
        ],
        ignore_index=True,
    )
    prices["effective_from"] = pd.to_datetime(prices["effective_from"])
    prices["effective_to"] = pd.to_datetime(prices["effective_to"])
    return icps, consumption, prices


def build_charge_quantities(
    consumption: pd.DataFrame, icps: pd.DataFrame
) -> pd.DataFrame:
    """Convert one monthly row into six component-level charge quantities."""
    base = consumption.merge(
        icps[
            [
                "icp_id",
                "retailer_id",
                "connection_group",
                "control_type",
                "price_category_code",
                "region",
            ]
        ],
        on="icp_id",
        how="left",
        validate="many_to_one",
    )

    # Fixed charges use connection days, not electricity consumption.
    fixed = base[
        [
            "consumption_id",
            "icp_id",
            "retailer_id",
            "connection_group",
            "control_type",
            "price_category_code",
            "region",
            "billing_month",
            "billing_period_start",
            "billing_period_end",
            "icp_days",
        ]
    ].copy()
    fixed["component_name"] = "Fixed Daily Charge"
    fixed["quantity"] = fixed["icp_days"].astype(float)
    fixed["quantity_unit"] = "connection days"

    # Variable components use kWh. Melt turns five time-band columns into rows,
    # giving one consistent component-level billing structure.
    identifier_columns = [
        "consumption_id",
        "icp_id",
        "retailer_id",
        "connection_group",
        "control_type",
        "price_category_code",
        "region",
        "billing_month",
        "billing_period_start",
        "billing_period_end",
        "icp_days",
    ]
    variable = base.melt(
        id_vars=identifier_columns,
        value_vars=list(VARIABLE_COMPONENT_MAP),
        var_name="consumption_field",
        value_name="quantity",
    )
    variable["component_name"] = variable["consumption_field"].map(
        VARIABLE_COMPONENT_MAP
    )
    variable["quantity_unit"] = "kWh"
    variable = variable.drop(columns="consumption_field")

    return pd.concat([fixed, variable], ignore_index=True)


def attach_applicable_prices(
    quantities: pd.DataFrame, prices: pd.DataFrame
) -> pd.DataFrame:
    """Join each quantity to its category/component price and verify validity."""
    # Our first-version billing periods are full calendar months and do not
    # cross 1 April. Selecting by period start is therefore valid for this scope.
    quantities = quantities.copy()
    quantities["price_year"] = quantities["billing_period_start"].apply(
        lambda date: 2025 if date < pd.Timestamp("2026-04-01") else 2026
    )

    price_columns = [
        "price_year",
        "effective_from",
        "effective_to",
        "price_category_code",
        "component_name",
        "component_code",
        "delivery_price",
        "unit",
    ]
    billed = quantities.merge(
        prices[price_columns],
        on=["price_year", "price_category_code", "component_name"],
        how="left",
        validate="many_to_one",
    )

    # The join keys select the price; these checks prove the selected price is
    # actually effective for the complete billing period.
    billed["effective_from"] = pd.to_datetime(billed["effective_from"])
    billed["effective_to"] = pd.to_datetime(billed["effective_to"])
    billed["price_effective_for_period"] = (
        billed["effective_from"].le(billed["billing_period_start"])
        & (
            billed["effective_to"].isna()
            | billed["effective_to"].ge(billed["billing_period_end"])
        )
    )

    # Retain unrounded arithmetic for reconciliation. The monthly bill is
    # rounded to cents only after all component charges have been summed.
    billed["expected_charge_unrounded"] = (
        billed["quantity"] * billed["delivery_price"]
    )
    billed["expected_charge_display"] = billed[
        "expected_charge_unrounded"
    ].round(5)
    billed["data_origin"] = "Calculated from public prices and simulated quantities"

    return billed.sort_values(
        ["billing_period_start", "icp_id", "component_name"]
    ).reset_index(drop=True)


def build_monthly_summary(detail: pd.DataFrame) -> pd.DataFrame:
    """Aggregate component charges to one monthly delivery charge per ICP."""
    group_columns = [
        "consumption_id",
        "icp_id",
        "retailer_id",
        "price_category_code",
        "region",
        "billing_month",
        "billing_period_start",
        "billing_period_end",
        "icp_days",
        "price_year",
    ]
    summary = (
        detail.groupby(group_columns, as_index=False)
        .agg(
            expected_delivery_charge_unrounded=("expected_charge_unrounded", "sum"),
            component_count=("component_code", "count"),
        )
        .sort_values(["billing_period_start", "icp_id"])
    )
    summary["expected_delivery_charge"] = summary[
        "expected_delivery_charge_unrounded"
    ].round(2)
    summary["data_origin"] = "Calculated from public prices and simulated quantities"
    return summary


def validation_result(test_id: str, name: str, passed: bool, detail: str) -> dict:
    return {
        "test_id": test_id,
        "test_name": name,
        "test_status": "PASS" if passed else "FAIL",
        "detail": detail,
    }


def validate_billing(
    detail: pd.DataFrame, summary: pd.DataFrame, consumption: pd.DataFrame
) -> pd.DataFrame:
    """Test completeness, pricing validity, units and billing arithmetic."""
    results = []
    results.append(
        validation_result(
            "B01",
            "Expected component-detail row count",
            len(detail) == 12000,
            f"Found {len(detail):,}; expected 2,000 months x 6 components",
        )
    )
    results.append(
        validation_result(
            "B02",
            "Expected monthly-summary row count",
            len(summary) == 2000,
            f"Found {len(summary):,}",
        )
    )
    results.append(
        validation_result(
            "B03",
            "No missing price matches",
            detail["component_code"].notna().all(),
            f"Missing matches: {detail['component_code'].isna().sum()}",
        )
    )
    results.append(
        validation_result(
            "B04",
            "Prices effective for complete billing periods",
            detail["price_effective_for_period"].all(),
            f"Invalid period matches: {(~detail['price_effective_for_period']).sum()}",
        )
    )

    unit_matches = (
        (detail["quantity_unit"].eq("connection days") & detail["unit"].eq("$/con/day"))
        | (detail["quantity_unit"].eq("kWh") & detail["unit"].eq("$/kWh"))
    )
    results.append(
        validation_result(
            "B05",
            "Quantity and price units match",
            unit_matches.all(),
            f"Unit mismatches: {(~unit_matches).sum()}",
        )
    )
    results.append(
        validation_result(
            "B06",
            "Six components per monthly bill",
            summary["component_count"].eq(6).all(),
            f"Incorrect summaries: {(~summary['component_count'].eq(6)).sum()}",
        )
    )

    summary_recalc = (
        detail.groupby("consumption_id")["expected_charge_unrounded"].sum().round(8)
    )
    stored_summary = summary.set_index("consumption_id")[
        "expected_delivery_charge_unrounded"
    ].round(8)
    arithmetic_matches = summary_recalc.eq(stored_summary)
    results.append(
        validation_result(
            "B07",
            "Monthly charges reconcile to component detail",
            arithmetic_matches.all(),
            f"Non-reconciling bills: {(~arithmetic_matches).sum()}",
        )
    )

    expected_year = summary["billing_period_start"].apply(
        lambda date: 2025 if date < pd.Timestamp("2026-04-01") else 2026
    )
    results.append(
        validation_result(
            "B08",
            "Price year selected at 1 April boundary",
            expected_year.eq(summary["price_year"]).all(),
            f"Wrong price years: {(~expected_year.eq(summary['price_year'])).sum()}",
        )
    )

    super_off_peak = detail.loc[detail["component_name"] == "Super Off Peak"]
    zero_rate_ok = (
        super_off_peak["delivery_price"].eq(0).all()
        and super_off_peak["expected_charge_unrounded"].eq(0).all()
    )
    results.append(
        validation_result(
            "B09",
            "Super Off Peak retained at zero charge",
            zero_rate_ok,
            f"Rows checked: {len(super_off_peak):,}",
        )
    )

    source_ids = set(consumption["consumption_id"])
    output_ids = set(summary["consumption_id"])
    results.append(
        validation_result(
            "B10",
            "Every source month appears once in billing summary",
            source_ids == output_ids and summary["consumption_id"].is_unique,
            f"Source IDs: {len(source_ids):,}; output IDs: {len(output_ids):,}",
        )
    )
    return pd.DataFrame(results)


def main() -> None:
    icps, consumption, prices = load_inputs()
    quantities = build_charge_quantities(consumption, icps)
    detail = attach_applicable_prices(quantities, prices)
    summary = build_monthly_summary(detail)
    tests = validate_billing(detail, summary, consumption)

    failed = tests.loc[tests["test_status"] == "FAIL"]
    if not failed.empty:
        print("EXPECTED BILLING VALIDATION FAILED")
        for row in failed.itertuples(index=False):
            print(f"- {row.test_id} {row.test_name}: {row.detail}")
        sys.exit(1)

    OUTPUT.mkdir(parents=True, exist_ok=True)
    TESTS.mkdir(parents=True, exist_ok=True)
    detail.to_csv(DETAIL_OUTPUT, index=False)
    summary.to_csv(SUMMARY_OUTPUT, index=False)
    tests.to_csv(TEST_OUTPUT, index=False)

    print("EXPECTED BILLING VALIDATION PASSED")
    print(f"- component-level rows: {len(detail):,}")
    print(f"- monthly bills: {len(summary):,}")
    print(f"- tests passed: {len(tests)}")
    print(
        "- expected delivery charges: "
        f"${summary['expected_delivery_charge_unrounded'].sum():,.2f}"
    )


if __name__ == "__main__":
    main()
