from pathlib import Path
import sys

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
FILES = [
    ROOT / "data" / "reference" / "price_schedule_2025.csv",
    ROOT / "data" / "reference" / "price_schedule_2026.csv",
]
EXPECTED_CATEGORIES = {"URES", "RES", "RSU", "RSC"}
EXPECTED_COMPONENTS = {
    "Fixed Daily Charge",
    "Weekend",
    "Peak",
    "Shoulder",
    "Off Peak",
    "Super Off Peak",
}
# Published component prices are rounded individually. A difference of up to
# $0.00010 between their displayed sum and the published delivery price is
# therefore treated as an accepted source-rounding difference.
TOLERANCE = 0.000101


def validate() -> list[str]:
    frames = [pd.read_csv(path) for path in FILES]
    prices = pd.concat(frames, ignore_index=True)
    errors: list[str] = []

    if len(prices) != 48:
        errors.append(f"Expected 48 price rows, found {len(prices)}")

    duplicate_count = prices.duplicated(["price_year", "component_code"]).sum()
    if duplicate_count:
        errors.append(f"Found {duplicate_count} duplicate year/component-code rows")

    for year, group in prices.groupby("price_year"):
        categories = set(group["price_category_code"])
        if categories != EXPECTED_CATEGORIES:
            errors.append(f"{year}: unexpected category set {sorted(categories)}")

        for category, category_rows in group.groupby("price_category_code"):
            components = set(category_rows["component_name"])
            if components != EXPECTED_COMPONENTS:
                errors.append(f"{year} {category}: unexpected components {sorted(components)}")

    component_sum = (
        prices["distribution_price"]
        + prices["pass_through_recoverable_price"]
        + prices["transmission_price"]
    )
    difference = (component_sum - prices["delivery_price"]).abs()
    bad_sums = prices.loc[difference > TOLERANCE, ["price_year", "component_code"]]
    for row in bad_sums.itertuples(index=False):
        errors.append(f"{row.price_year} {row.component_code}: delivery-price components do not sum")

    fixed_units = set(prices.loc[prices["component_name"] == "Fixed Daily Charge", "unit"])
    variable_units = set(prices.loc[prices["component_name"] != "Fixed Daily Charge", "unit"])
    if fixed_units != {"$/con/day"}:
        errors.append(f"Unexpected fixed-charge units: {sorted(fixed_units)}")
    if variable_units != {"$/kWh"}:
        errors.append(f"Unexpected variable-charge units: {sorted(variable_units)}")

    date_checks = {
        2025: ("2025-04-01", "2026-03-31"),
        2026: ("2026-04-01", None),
    }
    for year, (expected_from, expected_to) in date_checks.items():
        group = prices.loc[prices["price_year"] == year]
        actual_from = set(group["effective_from"])
        if actual_from != {expected_from}:
            errors.append(f"{year}: unexpected effective_from {sorted(actual_from)}")
        if expected_to is not None and set(group["effective_to"].dropna()) != {expected_to}:
            errors.append(f"{year}: unexpected effective_to values")
        if expected_to is None and group["effective_to"].notna().any():
            errors.append(f"{year}: expected open-ended effective_to")

    return errors


if __name__ == "__main__":
    validation_errors = validate()
    if validation_errors:
        print("PRICE VALIDATION FAILED")
        for validation_error in validation_errors:
            print(f"- {validation_error}")
        sys.exit(1)

    print("PRICE VALIDATION PASSED")
    print("- 48 rows checked across 2025 and 2026")
    print("- 4 price categories and 6 components per category/year")
    print("- component codes unique within each price year")
    print("- delivery prices reconcile to their three price components")
    print("- units and effective dates valid")
