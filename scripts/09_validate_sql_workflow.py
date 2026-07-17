from pathlib import Path
import sqlite3
import sys

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "data" / "reference"
SIMULATED = ROOT / "data" / "simulated"
OUTPUT = ROOT / "data" / "output"
SQL = ROOT / "sql"
TESTS = ROOT / "tests"
TEST_OUTPUT = TESTS / "sql_workflow_validation_results.csv"


def load_table(connection: sqlite3.Connection, name: str, path: Path) -> None:
    """Load one project CSV into an in-memory SQLite table."""
    frame = pd.read_csv(path)
    # Empty effective_to values must become SQL NULL so open-ended date logic
    # behaves correctly in the price-effective join.
    frame = frame.where(pd.notna(frame), None)
    frame.to_sql(name, connection, index=False, if_exists="replace")


def prepare_database(connection: sqlite3.Connection) -> None:
    price_schedule_all = pd.concat(
        [
            pd.read_csv(REFERENCE / "price_schedule_2025.csv"),
            pd.read_csv(REFERENCE / "price_schedule_2026.csv"),
        ],
        ignore_index=True,
    ).where(lambda frame: pd.notna(frame), None)
    price_schedule_all.to_sql(
        "price_schedule_all", connection, index=False, if_exists="replace"
    )

    load_table(connection, "retailer_master", SIMULATED / "retailer_master.csv")
    load_table(connection, "icp_master", SIMULATED / "icp_master.csv")
    load_table(connection, "monthly_consumption", SIMULATED / "monthly_consumption.csv")
    load_table(connection, "system_billing", SIMULATED / "system_billing.csv")

    for script_name in [
        "01_expected_billing.sql",
        "02_data_quality_checks.sql",
        "03_billing_reconciliation.sql",
        "04_reporting_views.sql",
    ]:
        connection.executescript((SQL / script_name).read_text(encoding="utf-8"))


def build_test_results(connection: sqlite3.Connection) -> pd.DataFrame:
    sql_expected = pd.read_sql_query(
        "SELECT * FROM vw_expected_billing_summary_sql", connection
    )
    python_expected = pd.read_csv(OUTPUT / "expected_billing_summary.csv")
    comparison = sql_expected[[
        "consumption_id", "expected_delivery_charge_unrounded"
    ]].merge(
        python_expected[["consumption_id", "expected_delivery_charge_unrounded"]],
        on="consumption_id",
        how="outer",
        suffixes=("_sql", "_python"),
        indicator=True,
        validate="one_to_one",
    )
    comparison["absolute_difference"] = (
        comparison["expected_delivery_charge_unrounded_sql"]
        - comparison["expected_delivery_charge_unrounded_python"]
    ).abs()

    reconciliation = pd.read_sql_query(
        "SELECT * FROM vw_billing_reconciliation_sql", connection
    )
    monthly = pd.read_sql_query(
        "SELECT * FROM vw_monthly_revenue_performance_sql", connection
    )
    quality = pd.read_sql_query(
        "SELECT * FROM vw_sql_data_quality_results", connection
    )

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

    add("SQL01", "SQL expected monthly bill count", len(sql_expected) == 2000, f"Found {len(sql_expected)}")
    add("SQL02", "SQL and Python bill keys match", comparison["_merge"].eq("both").all(), comparison["_merge"].value_counts().to_dict().__str__())
    max_difference = comparison["absolute_difference"].max()
    add("SQL03", "SQL and Python expected amounts match", max_difference <= 0.0000001, f"Maximum difference: {max_difference:.10f}")
    add("SQL04", "SQL component count", sql_expected["component_count"].eq(6).all(), f"Incorrect bills: {(~sql_expected['component_count'].eq(6)).sum()}")
    add("SQL05", "SQL reconciliation bill count", len(reconciliation) == 2000, f"Found {len(reconciliation)}")
    add("SQL06", "SQL review count", reconciliation["validation_status"].eq("REVIEW").sum() == 50, f"Found {reconciliation['validation_status'].eq('REVIEW').sum()}")
    add("SQL07", "SQL monthly reporting rows", len(monthly) == 4, f"Found {len(monthly)}")
    add("SQL08", "SQL data-quality failures", quality["failure_count"].sum() == 0, f"Total failures: {quality['failure_count'].sum()}")
    return pd.DataFrame(results)


def main() -> None:
    # An in-memory database proves the SQL scripts execute without leaving a
    # generated database file in the project.
    with sqlite3.connect(":memory:") as connection:
        prepare_database(connection)
        results = build_test_results(connection)

    failed = results.loc[results["test_status"] == "FAIL"]
    TESTS.mkdir(parents=True, exist_ok=True)
    results.to_csv(TEST_OUTPUT, index=False)
    if not failed.empty:
        print("SQL WORKFLOW VALIDATION FAILED")
        for row in failed.itertuples(index=False):
            print(f"- {row.test_id} {row.test_name}: {row.detail}")
        sys.exit(1)

    print("SQL WORKFLOW VALIDATION PASSED")
    print(f"- SQL tests passed: {len(results)}")
    print("- SQL expected billing matches Python expected billing")
    print("- SQL reconciliation identifies 50 REVIEW bills")


if __name__ == "__main__":
    main()
