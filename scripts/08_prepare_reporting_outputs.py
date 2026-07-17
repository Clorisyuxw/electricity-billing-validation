from pathlib import Path
import sys

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "data" / "reference"
SIMULATED = ROOT / "data" / "simulated"
OUTPUT = ROOT / "data" / "output"
TESTS = ROOT / "tests"

PRICE_IMPACT_OUTPUT = OUTPUT / "pricing_impact_analysis.csv"
MONTHLY_OUTPUT = OUTPUT / "revenue_monthly_summary.csv"
RETAILER_OUTPUT = OUTPUT / "retailer_performance_summary.csv"
CATEGORY_OUTPUT = OUTPUT / "category_performance_summary.csv"
TEST_OUTPUT = TESTS / "reporting_output_validation_results.csv"


def build_price_impact() -> pd.DataFrame:
    """Measure rate-only impact while holding each bill's quantities constant."""
    detail = pd.read_csv(
        OUTPUT / "expected_billing_detail.csv",
        parse_dates=["billing_period_start", "billing_period_end"],
    )
    prices_2025 = pd.read_csv(REFERENCE / "price_schedule_2025.csv")
    prices_2026 = pd.read_csv(REFERENCE / "price_schedule_2026.csv")

    # Only post-change months are needed. For every component quantity in April
    # and May, calculate two counterfactual amounts: one using 2025 rates and
    # one using 2026 rates. Consumption, category and days remain unchanged.
    post_change = detail.loc[detail["billing_month"].isin(["2026-04", "2026-05"])].copy()
    key = ["price_category_code", "component_name"]
    old_rates = prices_2025[key + ["delivery_price"]].rename(
        columns={"delivery_price": "delivery_price_2025"}
    )
    new_rates = prices_2026[key + ["delivery_price"]].rename(
        columns={"delivery_price": "delivery_price_2026"}
    )
    post_change = post_change.merge(old_rates, on=key, how="left", validate="many_to_one")
    post_change = post_change.merge(new_rates, on=key, how="left", validate="many_to_one")
    post_change["charge_at_2025_rates"] = (
        post_change["quantity"] * post_change["delivery_price_2025"]
    )
    post_change["charge_at_2026_rates"] = (
        post_change["quantity"] * post_change["delivery_price_2026"]
    )

    group_columns = [
        "consumption_id",
        "icp_id",
        "retailer_id",
        "price_category_code",
        "region",
        "billing_month",
    ]
    impact = (
        post_change.groupby(group_columns, as_index=False)
        .agg(
            charge_at_2025_rates=("charge_at_2025_rates", "sum"),
            charge_at_2026_rates=("charge_at_2026_rates", "sum"),
        )
        .sort_values(["billing_month", "icp_id"])
    )
    impact["price_change_impact"] = (
        impact["charge_at_2026_rates"] - impact["charge_at_2025_rates"]
    )
    impact["price_change_impact_pct"] = (
        impact["price_change_impact"] / impact["charge_at_2025_rates"] * 100
    )
    impact["charge_at_2025_rates"] = impact["charge_at_2025_rates"].round(5)
    impact["charge_at_2026_rates"] = impact["charge_at_2026_rates"].round(5)
    impact["price_change_impact"] = impact["price_change_impact"].round(5)
    impact["price_change_impact_pct"] = impact["price_change_impact_pct"].round(2)
    impact["analysis_basis"] = "Same quantities and categories; price schedule changed only"
    return impact


def load_reporting_base() -> pd.DataFrame:
    reconciliation = pd.read_csv(OUTPUT / "billing_reconciliation.csv")
    # The current reconciliation output already carries total_kwh for a simpler
    # Power BI fact table. Keep this fallback for older generated outputs.
    if "total_kwh" in reconciliation.columns:
        return reconciliation
    consumption = pd.read_csv(SIMULATED / "monthly_consumption.csv")
    return reconciliation.merge(
        consumption[["consumption_id", "total_kwh"]],
        on="consumption_id",
        how="left",
        validate="one_to_one",
    )


def aggregate_performance(base: pd.DataFrame, group_columns: list[str]) -> pd.DataFrame:
    """Apply one consistent KPI definition across month, retailer and category."""
    base = base.copy()
    # Reconciliation already defines one cent as the materiality threshold.
    # Apply the same rule to reporting so floating-point noise cannot appear as
    # a tiny over/underbilling amount or as negative zero after formatting.
    base["material_billing_variance"] = base["billing_variance_unrounded"].where(
        base["billing_variance_unrounded"].abs().gt(0.01), 0.0
    )
    grouped = (
        base.groupby(group_columns, as_index=False)
        .agg(
            bill_count=("consumption_id", "count"),
            total_consumption_kwh=("total_kwh", "sum"),
            expected_revenue=("expected_delivery_charge_unrounded", "sum"),
            system_billed_revenue=("system_billed_amount_unrounded", "sum"),
            net_billing_variance=("material_billing_variance", "sum"),
            total_absolute_variance=("material_billing_variance", lambda values: values.abs().sum()),
            exception_count=("validation_status", lambda values: values.eq("REVIEW").sum()),
            overbilled_amount=("material_billing_variance", lambda values: values.clip(lower=0).sum()),
            underbilled_amount=("material_billing_variance", lambda values: values.lt(0).mul(-values).sum()),
        )
        .sort_values(group_columns)
    )
    grouped["passed_bill_count"] = grouped["bill_count"] - grouped["exception_count"]
    grouped["billing_accuracy_rate_pct"] = (
        grouped["passed_bill_count"] / grouped["bill_count"] * 100
    ).round(2)
    grouped["exception_rate_pct"] = (
        grouped["exception_count"] / grouped["bill_count"] * 100
    ).round(2)

    money_columns = [
        "expected_revenue",
        "system_billed_revenue",
        "net_billing_variance",
        "total_absolute_variance",
        "overbilled_amount",
        "underbilled_amount",
    ]
    grouped[money_columns] = grouped[money_columns].round(2)
    grouped["total_consumption_kwh"] = grouped["total_consumption_kwh"].round(3)
    return grouped


def validate_reporting_outputs(
    impact: pd.DataFrame,
    monthly: pd.DataFrame,
    retailer: pd.DataFrame,
    category: pd.DataFrame,
) -> pd.DataFrame:
    tests = []

    def add(test_id: str, name: str, passed: bool, detail: str) -> None:
        tests.append(
            {
                "test_id": test_id,
                "test_name": name,
                "test_status": "PASS" if passed else "FAIL",
                "detail": detail,
            }
        )

    add("P01", "Price-impact bill count", len(impact) == 1000, f"Found {len(impact)}")
    add("P02", "Price-impact months", set(impact["billing_month"]) == {"2026-04", "2026-05"}, str(sorted(impact["billing_month"].unique())))
    add("P03", "No missing scenario rates", impact[["charge_at_2025_rates", "charge_at_2026_rates"]].notna().all().all(), "Both scenarios populated")
    # The three displayed fields are rounded independently to five decimals,
    # so a one-unit difference in the final displayed decimal is acceptable.
    impact_arithmetic = (
        impact["charge_at_2026_rates"]
        .sub(impact["charge_at_2025_rates"])
        .sub(impact["price_change_impact"])
        .abs()
        .le(0.000011)
    )
    add("P04", "Price-impact arithmetic", impact_arithmetic.all(), f"Incorrect rows: {(~impact_arithmetic).sum()}")
    add("P05", "Monthly summary row count", len(monthly) == 4, f"Found {len(monthly)}")
    add("P06", "Retailer summary row count", len(retailer) == 5, f"Found {len(retailer)}")
    add("P07", "Category summary row count", len(category) == 4, f"Found {len(category)}")
    add("P08", "Monthly bills total", monthly["bill_count"].sum() == 2000, f"Found {monthly['bill_count'].sum()}")
    add("P09", "Monthly exceptions total", monthly["exception_count"].sum() == 50, f"Found {monthly['exception_count'].sum()}")
    # Independently displayed currency totals can differ by one cent after
    # rounding even though their unrounded source values reconcile exactly.
    variance_identity = (
        monthly["system_billed_revenue"]
        .sub(monthly["expected_revenue"])
        .sub(monthly["net_billing_variance"])
        .abs()
        .le(0.011)
    )
    add("P10", "Monthly revenue variance identity", variance_identity.all(), f"Incorrect months: {(~variance_identity).sum()}")
    return pd.DataFrame(tests)


def main() -> None:
    price_impact = build_price_impact()
    base = load_reporting_base()
    monthly = aggregate_performance(base, ["billing_month", "price_year"])
    retailer = aggregate_performance(base, ["retailer_id"])
    category = aggregate_performance(base, ["price_category_code"])
    tests = validate_reporting_outputs(price_impact, monthly, retailer, category)

    failed = tests.loc[tests["test_status"] == "FAIL"]
    if not failed.empty:
        print("REPORTING OUTPUT VALIDATION FAILED")
        for row in failed.itertuples(index=False):
            print(f"- {row.test_id} {row.test_name}: {row.detail}")
        sys.exit(1)

    OUTPUT.mkdir(parents=True, exist_ok=True)
    TESTS.mkdir(parents=True, exist_ok=True)
    price_impact.to_csv(PRICE_IMPACT_OUTPUT, index=False)
    monthly.to_csv(MONTHLY_OUTPUT, index=False)
    retailer.to_csv(RETAILER_OUTPUT, index=False)
    category.to_csv(CATEGORY_OUTPUT, index=False)
    tests.to_csv(TEST_OUTPUT, index=False)

    print("REPORTING OUTPUT VALIDATION PASSED")
    print(f"- price-impact bills: {len(price_impact):,}")
    print(f"- monthly summaries: {len(monthly)}")
    print(f"- retailer summaries: {len(retailer)}")
    print(f"- category summaries: {len(category)}")
    print(f"- reporting tests passed: {len(tests)}")
    print(f"- isolated price impact: ${price_impact['price_change_impact'].sum():,.2f}")


if __name__ == "__main__":
    main()
