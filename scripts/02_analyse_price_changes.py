from pathlib import Path
import sys

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "data" / "reference"
TESTS = ROOT / "tests"

PRICE_2025 = REFERENCE / "price_schedule_2025.csv"
PRICE_2026 = REFERENCE / "price_schedule_2026.csv"
CHANGE_OUTPUT = REFERENCE / "price_change_analysis.csv"
TEST_OUTPUT = TESTS / "price_effective_date_tests.csv"


def load_prices() -> tuple[pd.DataFrame, pd.DataFrame]:
    prices_2025 = pd.read_csv(PRICE_2025, parse_dates=["effective_from", "effective_to"])
    prices_2026 = pd.read_csv(PRICE_2026, parse_dates=["effective_from", "effective_to"])
    return prices_2025, prices_2026


def analyse_changes(prices_2025: pd.DataFrame, prices_2026: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "connection_group",
        "control_type",
        "price_category_code",
        "component_name",
        "component_code",
        "unit",
        "delivery_price",
    ]

    changes = prices_2025[columns].merge(
        prices_2026[columns],
        on=[
            "connection_group",
            "control_type",
            "price_category_code",
            "component_name",
            "component_code",
            "unit",
        ],
        how="outer",
        suffixes=("_2025", "_2026"),
        indicator=True,
        validate="one_to_one",
    )

    changes["component_status"] = changes["_merge"].map(
        {"both": "Existing", "left_only": "Discontinued", "right_only": "New"}
    )
    changes["price_change"] = (
        changes["delivery_price_2026"] - changes["delivery_price_2025"]
    )
    # A zero-to-zero price is unchanged. Treat it as 0% rather than producing
    # an undefined 0/0 value. Other divisions retain their normal result.
    changes["price_change_pct"] = (
        changes["price_change"] / changes["delivery_price_2025"] * 100
    )
    both_zero = (
        changes["delivery_price_2025"].eq(0)
        & changes["delivery_price_2026"].eq(0)
    )
    changes.loc[both_zero, "price_change_pct"] = 0.0

    changes["delivery_price_2025"] = changes["delivery_price_2025"].round(5)
    changes["delivery_price_2026"] = changes["delivery_price_2026"].round(5)
    changes["price_change"] = changes["price_change"].round(5)
    changes["price_change_pct"] = changes["price_change_pct"].round(2)

    return changes.drop(columns="_merge").sort_values(
        ["price_category_code", "component_name"]
    )


def select_applicable_price_year(prices: pd.DataFrame, billing_date: str) -> int:
    date = pd.Timestamp(billing_date)
    applicable = prices.loc[
        (prices["effective_from"] <= date)
        & (prices["effective_to"].isna() | (prices["effective_to"] >= date))
    ]
    years = applicable["price_year"].unique()
    if len(years) != 1:
        raise ValueError(
            f"Expected one applicable price year for {billing_date}; found {list(years)}"
        )
    return int(years[0])


def test_effective_dates(prices: pd.DataFrame) -> pd.DataFrame:
    cases = [
        ("2026-02-01", 2025, "February uses the 2025 schedule"),
        ("2026-03-31", 2025, "Last day of the 2025 schedule"),
        ("2026-04-01", 2026, "First day of the 2026 schedule"),
        ("2026-05-01", 2026, "May uses the 2026 schedule"),
    ]

    results = []
    for test_date, expected_year, description in cases:
        actual_year = select_applicable_price_year(prices, test_date)
        results.append(
            {
                "test_date": test_date,
                "description": description,
                "expected_price_year": expected_year,
                "actual_price_year": actual_year,
                "test_status": "PASS" if actual_year == expected_year else "FAIL",
            }
        )
    return pd.DataFrame(results)


def validate_outputs(changes: pd.DataFrame, tests: pd.DataFrame) -> list[str]:
    errors: list[str] = []

    if len(changes) != 24:
        errors.append(f"Expected 24 matched price components; found {len(changes)}")
    if not (changes["component_status"] == "Existing").all():
        errors.append("The selected scope contains an unexpected new or discontinued component")
    if changes[["delivery_price_2025", "delivery_price_2026"]].isna().any().any():
        errors.append("A selected component is missing a 2025 or 2026 price")
    if (tests["test_status"] != "PASS").any():
        errors.append("At least one effective-date test failed")

    low_user_fixed = changes.loc[changes["component_code"] == "URESUFXD"]
    if len(low_user_fixed) != 1:
        errors.append("Could not uniquely identify URESUFXD")
    elif abs(float(low_user_fixed.iloc[0]["delivery_price_2026"]) - 0.9) > 0.00001:
        errors.append("2026 URESUFXD does not match the published $0.90 rate")

    return errors


def main() -> None:
    prices_2025, prices_2026 = load_prices()
    all_prices = pd.concat([prices_2025, prices_2026], ignore_index=True)

    changes = analyse_changes(prices_2025, prices_2026)
    tests = test_effective_dates(all_prices)
    errors = validate_outputs(changes, tests)

    if errors:
        print("PRICE CHANGE ANALYSIS FAILED")
        for error in errors:
            print(f"- {error}")
        sys.exit(1)

    REFERENCE.mkdir(parents=True, exist_ok=True)
    TESTS.mkdir(parents=True, exist_ok=True)
    changes.to_csv(CHANGE_OUTPUT, index=False)
    tests.to_csv(TEST_OUTPUT, index=False)

    print("PRICE CHANGE ANALYSIS PASSED")
    print(f"- {len(changes)} price components compared")
    print("- 4 effective-date boundary tests passed")
    print(f"- output: {CHANGE_OUTPUT.relative_to(ROOT)}")
    print(f"- output: {TEST_OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
