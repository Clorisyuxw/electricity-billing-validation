"""Run the complete project workflow in the required order.

This convenience runner stops immediately if any step fails, so later outputs
cannot be produced from an invalid upstream dataset.
"""

from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parent
SCRIPTS = [
    "01_validate_price_schedules.py",
    "02_analyse_price_changes.py",
    "03_generate_simulated_data.py",
    "04_validate_input_data.py",
    "05_calculate_expected_billing.py",
    "06_generate_system_billing.py",
    "07_reconcile_billing.py",
    "08_prepare_reporting_outputs.py",
    "09_validate_sql_workflow.py",
]


def main() -> None:
    for script_name in SCRIPTS:
        print(f"\n=== Running {script_name} ===", flush=True)
        subprocess.run(
            [sys.executable, str(ROOT / "scripts" / script_name)],
            cwd=ROOT,
            check=True,
        )
    print("\nALL PROJECT STEPS PASSED")


if __name__ == "__main__":
    main()
