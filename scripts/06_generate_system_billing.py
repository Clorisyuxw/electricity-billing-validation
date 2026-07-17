from pathlib import Path
import sys

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "data" / "reference"
OUTPUT = ROOT / "data" / "output"
SIMULATED = ROOT / "data" / "simulated"
TESTS = ROOT / "tests"

EXPECTED_DETAIL = OUTPUT / "expected_billing_detail.csv"
EXPECTED_SUMMARY = OUTPUT / "expected_billing_summary.csv"
SYSTEM_DETAIL_OUTPUT = SIMULATED / "system_billing_detail.csv"
SYSTEM_SUMMARY_OUTPUT = SIMULATED / "system_billing.csv"
EXCEPTIONS_OUTPUT = SIMULATED / "injected_exceptions.csv"
TEST_OUTPUT = TESTS / "system_billing_generation_results.csv"

RANDOM_SEED = 20260717
EXCEPTIONS_PER_TYPE = 10
EXCEPTION_TYPES = [
    "OLD_PRICE_APPLIED",
    "WRONG_PRICE_CATEGORY",
    "INCORRECT_ICP_DAYS",
    "DUPLICATE_CONSUMPTION",
    "CALCULATION_ERROR",
]


def load_inputs() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    expected_detail = pd.read_csv(
        EXPECTED_DETAIL,
        parse_dates=["billing_period_start", "billing_period_end"],
    )
    expected_summary = pd.read_csv(
        EXPECTED_SUMMARY,
        parse_dates=["billing_period_start", "billing_period_end"],
    )
    prices = pd.concat(
        [
            pd.read_csv(REFERENCE / "price_schedule_2025.csv"),
            pd.read_csv(REFERENCE / "price_schedule_2026.csv"),
        ],
        ignore_index=True,
    )
    return expected_detail, expected_summary, prices


def initialise_system_detail(expected_detail: pd.DataFrame) -> pd.DataFrame:
    """Create a clean system output before any controlled errors are added."""
    system = expected_detail.copy()
    system = system.rename(
        columns={
            "price_category_code": "expected_price_category_code",
            "price_year": "expected_price_year",
            "component_code": "expected_component_code",
            "quantity": "expected_quantity",
            "delivery_price": "expected_delivery_price",
        }
    )
    system["applied_price_category_code"] = system["expected_price_category_code"]
    system["applied_price_year"] = system["expected_price_year"]
    system["system_component_code"] = system["expected_component_code"]
    system["system_quantity"] = system["expected_quantity"]
    system["system_delivery_price"] = system["expected_delivery_price"]
    system["system_charge_unrounded"] = (
        system["system_quantity"] * system["system_delivery_price"]
    )
    system["injected_exception_type"] = ""
    system["system_line_id"] = [f"SYS{i:07d}" for i in range(1, len(system) + 1)]
    return system


def select_disjoint_bills(
    rng: np.random.Generator, expected_summary: pd.DataFrame
) -> dict[str, list[str]]:
    """Select 50 different bills so each test bill has one known root cause."""
    selected: dict[str, list[str]] = {}
    used: set[str] = set()

    for exception_type in EXCEPTION_TYPES:
        candidates = expected_summary.loc[
            ~expected_summary["consumption_id"].isin(used), "consumption_id"
        ]
        if exception_type == "OLD_PRICE_APPLIED":
            # An old-price error only makes business sense after the new schedule
            # has become effective.
            candidates = expected_summary.loc[
                expected_summary["billing_month"].isin(["2026-04", "2026-05"])
                & ~expected_summary["consumption_id"].isin(used),
                "consumption_id",
            ]

        chosen = rng.choice(candidates.to_numpy(), size=EXCEPTIONS_PER_TYPE, replace=False)
        selected[exception_type] = chosen.tolist()
        used.update(chosen.tolist())

    return selected


def inject_old_prices(
    system: pd.DataFrame, selected_ids: list[str], prices: pd.DataFrame
) -> None:
    mask = system["consumption_id"].isin(selected_ids)
    old_prices = prices.loc[prices["price_year"] == 2025, [
        "price_category_code",
        "component_name",
        "component_code",
        "delivery_price",
    ]].rename(
        columns={
            "price_category_code": "applied_price_category_code",
            "component_code": "replacement_component_code",
            "delivery_price": "replacement_delivery_price",
        }
    )
    replacement = system.loc[mask, [
        "applied_price_category_code", "component_name"
    ]].merge(
        old_prices,
        on=["applied_price_category_code", "component_name"],
        how="left",
        validate="many_to_one",
    )
    if replacement["replacement_component_code"].isna().any():
        raise ValueError("Old-price injection could not find a 2025 component")

    system.loc[mask, "applied_price_year"] = 2025
    system.loc[mask, "system_component_code"] = replacement[
        "replacement_component_code"
    ].to_numpy()
    system.loc[mask, "system_delivery_price"] = replacement[
        "replacement_delivery_price"
    ].to_numpy()
    system.loc[mask, "system_charge_unrounded"] = (
        system.loc[mask, "system_quantity"]
        * system.loc[mask, "system_delivery_price"]
    )
    system.loc[mask, "injected_exception_type"] = "OLD_PRICE_APPLIED"


def inject_wrong_categories(
    system: pd.DataFrame, selected_ids: list[str], prices: pd.DataFrame
) -> None:
    # Swap within the same control type: uncontrolled URES <-> RSU and
    # controlled RES <-> RSC. This creates a plausible category-assignment error.
    alternative = {"URES": "RSU", "RSU": "URES", "RES": "RSC", "RSC": "RES"}
    mask = system["consumption_id"].isin(selected_ids)
    rows = system.loc[mask].copy()
    rows["wrong_category"] = rows["expected_price_category_code"].map(alternative)

    replacement_prices = prices[[
        "price_year",
        "price_category_code",
        "component_name",
        "component_code",
        "delivery_price",
    ]].rename(
        columns={
            "price_category_code": "wrong_category",
            "component_code": "replacement_component_code",
            "delivery_price": "replacement_delivery_price",
        }
    )
    replacement = rows.merge(
        replacement_prices,
        left_on=["expected_price_year", "wrong_category", "component_name"],
        right_on=["price_year", "wrong_category", "component_name"],
        how="left",
        validate="many_to_one",
    )
    if replacement["replacement_component_code"].isna().any():
        raise ValueError("Wrong-category injection could not find a replacement price")

    system.loc[mask, "applied_price_category_code"] = replacement[
        "wrong_category"
    ].to_numpy()
    system.loc[mask, "system_component_code"] = replacement[
        "replacement_component_code"
    ].to_numpy()
    system.loc[mask, "system_delivery_price"] = replacement[
        "replacement_delivery_price"
    ].to_numpy()
    system.loc[mask, "system_charge_unrounded"] = (
        system.loc[mask, "system_quantity"]
        * system.loc[mask, "system_delivery_price"]
    )
    system.loc[mask, "injected_exception_type"] = "WRONG_PRICE_CATEGORY"


def inject_incorrect_days(system: pd.DataFrame, selected_ids: list[str]) -> None:
    # Only the fixed line uses connection days. Add two days so the error is
    # unambiguous and has a measurable financial impact.
    mask = system["consumption_id"].isin(selected_ids) & system[
        "component_name"
    ].eq("Fixed Daily Charge")
    system.loc[mask, "system_quantity"] = system.loc[mask, "system_quantity"] + 2
    system.loc[mask, "system_charge_unrounded"] = (
        system.loc[mask, "system_quantity"]
        * system.loc[mask, "system_delivery_price"]
    )
    system.loc[mask, "injected_exception_type"] = "INCORRECT_ICP_DAYS"


def inject_duplicates(system: pd.DataFrame, selected_ids: list[str]) -> pd.DataFrame:
    # Duplicate the Peak line. The extra row imitates consumption being loaded
    # twice and makes both the record count and billed amount incorrect.
    duplicate_mask = system["consumption_id"].isin(selected_ids) & system[
        "component_name"
    ].eq("Peak")
    duplicates = system.loc[duplicate_mask].copy()
    duplicates["injected_exception_type"] = "DUPLICATE_CONSUMPTION"
    duplicates["system_line_id"] = [
        f"SYSDUP{i:04d}" for i in range(1, len(duplicates) + 1)
    ]
    return pd.concat([system, duplicates], ignore_index=True)


def inject_calculation_errors(system: pd.DataFrame, selected_ids: list[str]) -> None:
    # Quantities and rates remain correct, but the calculated fixed-line charge
    # is overstated by $5.25. Detection must recalculate quantity x price.
    mask = system["consumption_id"].isin(selected_ids) & system[
        "component_name"
    ].eq("Fixed Daily Charge")
    system.loc[mask, "system_charge_unrounded"] = (
        system.loc[mask, "system_charge_unrounded"] + 5.25
    )
    system.loc[mask, "injected_exception_type"] = "CALCULATION_ERROR"


def build_system_summary(system: pd.DataFrame) -> pd.DataFrame:
    summary = (
        system.groupby(
            [
                "consumption_id",
                "icp_id",
                "retailer_id",
                "billing_month",
                "billing_period_start",
                "billing_period_end",
                "icp_days",
                "expected_price_category_code",
                "expected_price_year",
            ],
            as_index=False,
        )
        .agg(
            system_billed_amount_unrounded=("system_charge_unrounded", "sum"),
            system_line_count=("system_line_id", "count"),
        )
        .sort_values(["billing_period_start", "icp_id"])
    )
    summary["system_billed_amount"] = summary[
        "system_billed_amount_unrounded"
    ].round(2)
    summary["data_origin"] = "Simulated system billing with controlled test exceptions"
    return summary


def build_exception_control(
    selections: dict[str, list[str]],
    expected_summary: pd.DataFrame,
    system_summary: pd.DataFrame,
) -> pd.DataFrame:
    exception_map = {
        consumption_id: exception_type
        for exception_type, ids in selections.items()
        for consumption_id in ids
    }
    control = expected_summary[
        ["consumption_id", "icp_id", "retailer_id", "billing_month", "expected_delivery_charge_unrounded"]
    ].merge(
        system_summary[["consumption_id", "system_billed_amount_unrounded"]],
        on="consumption_id",
        how="inner",
        validate="one_to_one",
    )
    control = control.loc[control["consumption_id"].isin(exception_map)].copy()
    control["injected_exception_type"] = control["consumption_id"].map(exception_map)
    control["injected_financial_impact"] = (
        control["system_billed_amount_unrounded"]
        - control["expected_delivery_charge_unrounded"]
    ).round(5)
    control.insert(0, "exception_id", [f"INJ{i:03d}" for i in range(1, len(control) + 1)])
    control["data_origin"] = "Controlled simulated exception"
    return control.sort_values(["injected_exception_type", "consumption_id"])


def test_generation(
    system_detail: pd.DataFrame,
    system_summary: pd.DataFrame,
    control: pd.DataFrame,
) -> pd.DataFrame:
    checks = []

    def add(test_id: str, name: str, passed: bool, detail: str) -> None:
        checks.append(
            {
                "test_id": test_id,
                "test_name": name,
                "test_status": "PASS" if passed else "FAIL",
                "detail": detail,
            }
        )

    add("S01", "System summary row count", len(system_summary) == 2000, f"Found {len(system_summary)}")
    add("S02", "System detail row count", len(system_detail) == 12010, f"Found {len(system_detail)}")
    add("S03", "Unique controlled exception bills", control["consumption_id"].nunique() == 50, f"Found {control['consumption_id'].nunique()}")
    counts = control["injected_exception_type"].value_counts()
    correct_counts = all(counts.get(kind, 0) == EXCEPTIONS_PER_TYPE for kind in EXCEPTION_TYPES)
    add("S04", "Ten bills per exception type", correct_counts, counts.to_dict().__str__())
    add("S05", "Exception impacts exceed one cent", control["injected_financial_impact"].abs().gt(0.01).all(), f"Minimum impact: {control['injected_financial_impact'].abs().min():.5f}")
    add("S06", "No missing system amounts", system_detail["system_charge_unrounded"].notna().all(), f"Missing: {system_detail['system_charge_unrounded'].isna().sum()}")
    add("S07", "Unique system line IDs", system_detail["system_line_id"].is_unique, f"Duplicates: {system_detail['system_line_id'].duplicated().sum()}")
    return pd.DataFrame(checks)


def main() -> None:
    rng = np.random.default_rng(RANDOM_SEED)
    expected_detail, expected_summary, prices = load_inputs()
    system = initialise_system_detail(expected_detail)
    selections = select_disjoint_bills(rng, expected_summary)

    inject_old_prices(system, selections["OLD_PRICE_APPLIED"], prices)
    inject_wrong_categories(system, selections["WRONG_PRICE_CATEGORY"], prices)
    inject_incorrect_days(system, selections["INCORRECT_ICP_DAYS"])
    system = inject_duplicates(system, selections["DUPLICATE_CONSUMPTION"])
    inject_calculation_errors(system, selections["CALCULATION_ERROR"])

    system_summary = build_system_summary(system)
    control = build_exception_control(selections, expected_summary, system_summary)
    tests = test_generation(system, system_summary, control)
    failed = tests.loc[tests["test_status"] == "FAIL"]
    if not failed.empty:
        print("SYSTEM BILLING GENERATION FAILED")
        for row in failed.itertuples(index=False):
            print(f"- {row.test_id} {row.test_name}: {row.detail}")
        sys.exit(1)

    SIMULATED.mkdir(parents=True, exist_ok=True)
    TESTS.mkdir(parents=True, exist_ok=True)
    system.to_csv(SYSTEM_DETAIL_OUTPUT, index=False)
    system_summary.to_csv(SYSTEM_SUMMARY_OUTPUT, index=False)
    control.to_csv(EXCEPTIONS_OUTPUT, index=False)
    tests.to_csv(TEST_OUTPUT, index=False)

    print("SYSTEM BILLING GENERATION PASSED")
    print(f"- system bills: {len(system_summary):,}")
    print(f"- system detail lines: {len(system):,}")
    print(f"- controlled exception bills: {len(control):,}")
    print(f"- generation tests passed: {len(tests)}")


if __name__ == "__main__":
    main()
