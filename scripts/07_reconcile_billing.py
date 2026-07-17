from pathlib import Path
import sys

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "output"
SIMULATED = ROOT / "data" / "simulated"
TESTS = ROOT / "tests"

EXPECTED_SUMMARY = OUTPUT / "expected_billing_summary.csv"
SYSTEM_DETAIL = SIMULATED / "system_billing_detail.csv"
SYSTEM_SUMMARY = SIMULATED / "system_billing.csv"
CONTROL_EXCEPTIONS = SIMULATED / "injected_exceptions.csv"

RECON_OUTPUT = OUTPUT / "billing_reconciliation.csv"
EXCEPTION_LOG_OUTPUT = OUTPUT / "billing_exception_log.csv"
TEST_OUTPUT = TESTS / "billing_reconciliation_validation_results.csv"

AMOUNT_TOLERANCE = 0.01
CALCULATION_TOLERANCE = 0.00001


def detect_issue_types(system_detail: pd.DataFrame) -> pd.Series:
    """Detect root cause from system fields without reading the answer table."""
    bill_ids = system_detail["consumption_id"].drop_duplicates()
    detected = pd.Series("NO_ISSUE", index=bill_ids, dtype="object")

    # More than one line for the same bill/component indicates duplicated input.
    duplicate_ids = system_detail.loc[
        system_detail.duplicated(["consumption_id", "component_name"], keep=False),
        "consumption_id",
    ].unique()
    detected.loc[duplicate_ids] = "DUPLICATE_CONSUMPTION"

    # The system should use the same price year selected by the expected-date rule.
    old_price_ids = system_detail.loc[
        system_detail["applied_price_year"].ne(system_detail["expected_price_year"]),
        "consumption_id",
    ].unique()
    detected.loc[old_price_ids] = "OLD_PRICE_APPLIED"

    # ICP master category and applied category must match on every component.
    wrong_category_ids = system_detail.loc[
        system_detail["applied_price_category_code"].ne(
            system_detail["expected_price_category_code"]
        ),
        "consumption_id",
    ].unique()
    detected.loc[wrong_category_ids] = "WRONG_PRICE_CATEGORY"

    # Fixed charge quantity must equal the inclusive ICP-day count.
    incorrect_days_ids = system_detail.loc[
        system_detail["component_name"].eq("Fixed Daily Charge")
        & system_detail["system_quantity"].ne(system_detail["icp_days"]),
        "consumption_id",
    ].unique()
    detected.loc[incorrect_days_ids] = "INCORRECT_ICP_DAYS"

    # Recalculate line amount independently from stored system amount.
    recalculated = (
        system_detail["system_quantity"] * system_detail["system_delivery_price"]
    )
    calculation_error_ids = system_detail.loc[
        (system_detail["system_charge_unrounded"] - recalculated)
        .abs()
        .gt(CALCULATION_TOLERANCE),
        "consumption_id",
    ].unique()
    detected.loc[calculation_error_ids] = "CALCULATION_ERROR"
    return detected


def build_reconciliation(
    expected: pd.DataFrame,
    system_summary: pd.DataFrame,
    system_detail: pd.DataFrame,
) -> pd.DataFrame:
    reconciliation = expected.merge(
        system_summary[
            [
                "consumption_id",
                "system_billed_amount_unrounded",
                "system_billed_amount",
                "system_line_count",
            ]
        ],
        on="consumption_id",
        how="outer",
        validate="one_to_one",
        indicator=True,
    )
    detected = detect_issue_types(system_detail)
    reconciliation["detected_issue_type"] = reconciliation["consumption_id"].map(
        detected
    )
    reconciliation["billing_variance_unrounded"] = (
        reconciliation["system_billed_amount_unrounded"]
        - reconciliation["expected_delivery_charge_unrounded"]
    )
    reconciliation["billing_variance"] = reconciliation[
        "billing_variance_unrounded"
    ].round(2)
    reconciliation["absolute_variance"] = reconciliation[
        "billing_variance_unrounded"
    ].abs().round(2)
    reconciliation["variance_direction"] = "No material variance"
    reconciliation.loc[
        reconciliation["billing_variance_unrounded"].gt(AMOUNT_TOLERANCE),
        "variance_direction",
    ] = "Overbilled"
    reconciliation.loc[
        reconciliation["billing_variance_unrounded"].lt(-AMOUNT_TOLERANCE),
        "variance_direction",
    ] = "Underbilled"
    reconciliation["validation_status"] = reconciliation[
        "billing_variance_unrounded"
    ].abs().le(AMOUNT_TOLERANCE).map({True: "PASS", False: "REVIEW"})
    reconciliation["data_origin"] = "Calculated reconciliation"
    return reconciliation.sort_values(["billing_period_start", "icp_id"])


def build_exception_log(reconciliation: pd.DataFrame) -> pd.DataFrame:
    action_map = {
        "OLD_PRICE_APPLIED": "Correct price version and rebill affected record",
        "WRONG_PRICE_CATEGORY": "Confirm ICP category, correct master data and rebill",
        "INCORRECT_ICP_DAYS": "Correct billable day count and recalculate fixed charge",
        "DUPLICATE_CONSUMPTION": "Remove duplicate component and rerun billing validation",
        "CALCULATION_ERROR": "Investigate calculation routine and recalculate charge",
    }
    exceptions = reconciliation.loc[reconciliation["validation_status"] == "REVIEW"].copy()
    exceptions["priority"] = pd.cut(
        exceptions["absolute_variance"],
        bins=[-0.01, 5, 20, float("inf")],
        labels=["Low", "Medium", "High"],
    ).astype(str)
    exceptions["recommended_action"] = exceptions["detected_issue_type"].map(action_map)
    exceptions["issue_status"] = "Open - Review Required"
    exceptions.insert(0, "issue_id", [f"ISS{i:03d}" for i in range(1, len(exceptions) + 1)])
    return exceptions[
        [
            "issue_id",
            "consumption_id",
            "icp_id",
            "retailer_id",
            "billing_month",
            "price_category_code",
            "expected_delivery_charge",
            "system_billed_amount",
            "billing_variance",
            "variance_direction",
            "detected_issue_type",
            "priority",
            "recommended_action",
            "issue_status",
        ]
    ]


def validate_detection(
    reconciliation: pd.DataFrame,
    exception_log: pd.DataFrame,
    control: pd.DataFrame,
    system_detail: pd.DataFrame,
) -> pd.DataFrame:
    results = []

    def add(test_id: str, name: str, passed: bool, detail: str) -> None:
        results.append(
            {
                "test_id": test_id,
                "test_name": name,
                "test_status": "PASS" if passed else "FAIL",
                "detail": detail,
            }
        )

    add("R01", "Reconciliation row count", len(reconciliation) == 2000, f"Found {len(reconciliation)}")
    add("R02", "Expected and system bills both present", reconciliation["_merge"].eq("both").all(), reconciliation["_merge"].value_counts().to_dict().__str__())
    add("R03", "Review count equals controlled exceptions", len(exception_log) == 50, f"Found {len(exception_log)}")
    add("R04", "Clean bills pass", reconciliation["validation_status"].eq("PASS").sum() == 1950, f"PASS: {reconciliation['validation_status'].eq('PASS').sum()}")

    detected = reconciliation[["consumption_id", "detected_issue_type"]].merge(
        control[["consumption_id", "injected_exception_type"]],
        on="consumption_id",
        how="outer",
        indicator=True,
    )
    controlled_rows = detected.loc[detected["_merge"] == "both"]
    classification_match = controlled_rows["detected_issue_type"].eq(
        controlled_rows["injected_exception_type"]
    )
    add("R05", "All controlled exceptions detected", len(controlled_rows) == 50, f"Detected controlled bills: {len(controlled_rows)}")
    add("R06", "Root-cause classification accuracy", classification_match.all(), f"Correct: {classification_match.sum()} of {len(classification_match)}")

    control_ids = set(control["consumption_id"])
    detected_issue_ids = set(
        reconciliation.loc[
            reconciliation["detected_issue_type"].ne("NO_ISSUE"), "consumption_id"
        ]
    )
    false_positives = detected_issue_ids - control_ids
    false_negatives = control_ids - detected_issue_ids
    add("R07", "No false-positive issue detection", not false_positives, f"False positives: {len(false_positives)}")
    add("R08", "No false-negative issue detection", not false_negatives, f"False negatives: {len(false_negatives)}")

    detail_sum = system_detail.groupby("consumption_id")["system_charge_unrounded"].sum().round(8)
    summary_sum = reconciliation.set_index("consumption_id")["system_billed_amount_unrounded"].round(8)
    add("R09", "System summary reconciles to detail", detail_sum.eq(summary_sum).all(), f"Non-reconciling: {(~detail_sum.eq(summary_sum)).sum()}")

    amount_control = reconciliation[["consumption_id", "billing_variance_unrounded"]].merge(
        control[["consumption_id", "injected_financial_impact"]],
        on="consumption_id",
        how="inner",
        validate="one_to_one",
    )
    amount_match = amount_control["billing_variance_unrounded"].round(5).eq(
        amount_control["injected_financial_impact"].round(5)
    )
    add("R10", "Detected financial impact matches control", amount_match.all(), f"Correct: {amount_match.sum()} of {len(amount_match)}")
    add(
        "R11",
        "Consumption quantity available for every reconciled bill",
        reconciliation["total_kwh"].notna().all(),
        f"Missing total_kwh: {reconciliation['total_kwh'].isna().sum()}",
    )
    return pd.DataFrame(results)


def main() -> None:
    expected = pd.read_csv(
        EXPECTED_SUMMARY,
        parse_dates=["billing_period_start", "billing_period_end"],
    )
    system_detail = pd.read_csv(SYSTEM_DETAIL, keep_default_na=False)
    system_summary = pd.read_csv(SYSTEM_SUMMARY)
    control = pd.read_csv(CONTROL_EXCEPTIONS)
    consumption = pd.read_csv(
        SIMULATED / "monthly_consumption.csv",
        usecols=["consumption_id", "total_kwh"],
    )

    reconciliation = build_reconciliation(expected, system_summary, system_detail)
    reconciliation = reconciliation.merge(
        consumption,
        on="consumption_id",
        how="left",
        validate="one_to_one",
    )
    exception_log = build_exception_log(reconciliation)
    tests = validate_detection(reconciliation, exception_log, control, system_detail)
    failed = tests.loc[tests["test_status"] == "FAIL"]
    if not failed.empty:
        print("BILLING RECONCILIATION FAILED")
        for row in failed.itertuples(index=False):
            print(f"- {row.test_id} {row.test_name}: {row.detail}")
        sys.exit(1)

    reconciliation = reconciliation.drop(columns="_merge")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    TESTS.mkdir(parents=True, exist_ok=True)
    reconciliation.to_csv(RECON_OUTPUT, index=False)
    exception_log.to_csv(EXCEPTION_LOG_OUTPUT, index=False)
    tests.to_csv(TEST_OUTPUT, index=False)

    print("BILLING RECONCILIATION PASSED")
    print(f"- bills reconciled: {len(reconciliation):,}")
    print(f"- PASS: {(reconciliation['validation_status'] == 'PASS').sum():,}")
    print(f"- REVIEW: {(reconciliation['validation_status'] == 'REVIEW').sum():,}")
    print("- controlled exception detection: 50 of 50")
    print("- false positives: 0")
    print("- false negatives: 0")


if __name__ == "__main__":
    main()
