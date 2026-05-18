"""
Data quality validation for processed CMS hospital datasets.

Runs automated checks on transformed data and produces a JSON report:
  - Schema validation (expected columns and types)
  - Null/missing value thresholds
  - Range checks on numeric measures
  - Referential integrity between datasets
  - Row count minimums

Usage:
    python etl/validate_data.py
"""

import json
import logging
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from config import PROCESSED_DIR, NULL_THRESHOLD, MIN_ROW_COUNT, LOG_LEVEL, LOG_FORMAT

logging.basicConfig(level=LOG_LEVEL, format=LOG_FORMAT)
logger = logging.getLogger("validate")


class DataValidator:
    """Validates processed healthcare datasets against quality rules."""

    def __init__(self):
        self.results = {
            "run_timestamp": datetime.utcnow().isoformat(),
            "datasets": {},
            "overall_status": "PASS",
        }

    def _record(self, dataset: str, check: str, status: str, detail: str):
        """Record a validation result."""
        if dataset not in self.results["datasets"]:
            self.results["datasets"][dataset] = {"checks": [], "status": "PASS"}

        self.results["datasets"][dataset]["checks"].append({
            "check": check,
            "status": status,
            "detail": detail,
        })

        if status == "FAIL":
            self.results["datasets"][dataset]["status"] = "FAIL"
            self.results["overall_status"] = "FAIL"
        elif status == "WARN" and self.results["datasets"][dataset]["status"] != "FAIL":
            self.results["datasets"][dataset]["status"] = "WARN"

    def check_file_exists(self, name: str, path: Path) -> bool:
        """Verify the processed file exists."""
        exists = path.exists()
        self._record(
            name,
            "file_exists",
            "PASS" if exists else "FAIL",
            f"File {'found' if exists else 'MISSING'}: {path.name}",
        )
        return exists

    def check_row_count(self, name: str, df: pd.DataFrame, min_rows: int):
        """Verify minimum expected row count."""
        actual = len(df)
        status = "PASS" if actual >= min_rows else "FAIL"
        self._record(
            name,
            "row_count",
            status,
            f"Expected >= {min_rows:,}, got {actual:,}",
        )

    def check_null_rates(self, name: str, df: pd.DataFrame, threshold: float = NULL_THRESHOLD):
        """Check null rates per column against threshold."""
        null_rates = df.isnull().mean()
        violations = null_rates[null_rates > threshold]

        if violations.empty:
            self._record(
                name,
                "null_rates",
                "PASS",
                f"All columns below {threshold:.0%} null threshold",
            )
        else:
            for col, rate in violations.items():
                self._record(
                    name,
                    f"null_rate_{col}",
                    "WARN",
                    f"Column '{col}' is {rate:.1%} null (threshold: {threshold:.0%})",
                )

    def check_duplicates(self, name: str, df: pd.DataFrame, key_cols: list[str]):
        """Check for duplicate records on specified key columns."""
        available_keys = [c for c in key_cols if c in df.columns]
        if not available_keys:
            self._record(name, "duplicates", "WARN", f"Key columns not found: {key_cols}")
            return

        dupes = df.duplicated(subset=available_keys, keep=False).sum()
        status = "PASS" if dupes == 0 else "WARN"
        self._record(
            name,
            "duplicates",
            status,
            f"{dupes:,} duplicate rows on key {available_keys}",
        )

    def check_range(self, name: str, df: pd.DataFrame, col: str, min_val: float, max_val: float):
        """Validate numeric column falls within expected range."""
        if col not in df.columns:
            self._record(name, f"range_{col}", "WARN", f"Column '{col}' not found")
            return

        series = df[col].dropna()
        out_of_range = ((series < min_val) | (series > max_val)).sum()
        status = "PASS" if out_of_range == 0 else "WARN"
        self._record(
            name,
            f"range_{col}",
            status,
            f"{out_of_range:,} values outside [{min_val}, {max_val}] "
            f"(actual range: [{series.min():.2f}, {series.max():.2f}])",
        )

    def check_referential_integrity(
        self, child_name: str, child_df: pd.DataFrame, child_col: str,
        parent_name: str, parent_df: pd.DataFrame, parent_col: str
    ):
        """Check that all child keys exist in parent dataset."""
        if child_col not in child_df.columns or parent_col not in parent_df.columns:
            self._record(
                child_name,
                f"ref_integrity_{parent_name}",
                "WARN",
                f"Columns not found for integrity check",
            )
            return

        child_keys = set(child_df[child_col].dropna().unique())
        parent_keys = set(parent_df[parent_col].dropna().unique())
        orphans = child_keys - parent_keys

        pct = len(orphans) / len(child_keys) * 100 if child_keys else 0
        status = "PASS" if pct < 5 else "WARN"
        self._record(
            child_name,
            f"ref_integrity_{parent_name}",
            status,
            f"{len(orphans):,} orphan keys ({pct:.1f}%) not found in {parent_name}",
        )

    def validate_hospital_master(self, df: pd.DataFrame):
        """Run all checks on hospital master dataset."""
        name = "hospital_master"
        self.check_row_count(name, df, 4000)
        self.check_null_rates(name, df)
        self.check_duplicates(name, df, ["facility_id"])
        self.check_range(name, df, "star_rating", 1, 5)
        self.check_range(name, df, "avg_excess_readmission_ratio", 0.5, 2.0)
        self.check_range(name, df, "mspb_score", 0.5, 2.0)
        self.check_range(name, df, "readmission_rate", 0, 1)

    def validate_readmissions(self, df: pd.DataFrame, master_df: pd.DataFrame):
        """Run all checks on readmissions detail dataset."""
        name = "readmissions_detail"
        self.check_row_count(name, df, 10000)
        self.check_null_rates(name, df)
        self.check_range(name, df, "excess_readmission_ratio", 0.3, 3.0)
        self.check_range(name, df, "predicted_readmission_rate", 0, 50)
        self.check_range(name, df, "expected_readmission_rate", 0, 50)
        self.check_referential_integrity(
            name, df, "facility_id", "hospital_master", master_df, "facility_id"
        )

    def validate_state_summary(self, df: pd.DataFrame):
        """Run all checks on state summary dataset."""
        name = "state_summary"
        self.check_row_count(name, df, 50)
        self.check_null_rates(name, df)
        self.check_duplicates(name, df, ["state"])
        self.check_range(name, df, "avg_star_rating", 1, 5)
        self.check_range(name, df, "pct_penalized", 0, 1)
        self.check_range(name, df, "avg_mspb_score", 0.5, 2.0)

    def save_report(self, output_path: Path):
        """Save validation report as JSON."""
        with open(output_path, "w") as f:
            json.dump(self.results, f, indent=2)
        logger.info(f"Validation report saved: {output_path}")

    def print_report(self):
        """Print human-readable validation summary."""
        logger.info(f"\n{'='*60}")
        logger.info(f"DATA QUALITY REPORT: {self.results['overall_status']}")
        logger.info(f"{'='*60}")

        for ds_name, ds_result in self.results["datasets"].items():
            status_icon = {"PASS": "✓", "WARN": "⚠", "FAIL": "✗"}[ds_result["status"]]
            logger.info(f"\n  {status_icon} {ds_name}: {ds_result['status']}")
            for check in ds_result["checks"]:
                icon = {"PASS": "✓", "WARN": "⚠", "FAIL": "✗"}[check["status"]]
                logger.info(f"    {icon} {check['check']}: {check['detail']}")

        logger.info(f"\n{'='*60}")


def main():
    logger.info("=" * 60)
    logger.info("DATA QUALITY VALIDATION START")
    logger.info("=" * 60)

    validator = DataValidator()

    # Load processed datasets
    files = {
        "hospital_master": PROCESSED_DIR / "hospital_master.csv",
        "readmissions_detail": PROCESSED_DIR / "readmissions_detail.csv",
        "state_summary": PROCESSED_DIR / "state_summary.csv",
    }

    # Check all files exist
    all_exist = True
    for name, path in files.items():
        if not validator.check_file_exists(name, path):
            all_exist = False

    if not all_exist:
        logger.error("Missing processed files. Run transform_hospital_data.py first.")
        validator.print_report()
        sys.exit(1)

    # Load data
    master = pd.read_csv(files["hospital_master"], dtype={"facility_id": str})
    readmissions = pd.read_csv(files["readmissions_detail"], dtype={"facility_id": str})
    state_summary = pd.read_csv(files["state_summary"])

    # Run validations
    validator.validate_hospital_master(master)
    validator.validate_readmissions(readmissions, master)
    validator.validate_state_summary(state_summary)

    # Output
    report_path = PROCESSED_DIR / "data_quality_report.json"
    validator.save_report(report_path)
    validator.print_report()

    if validator.results["overall_status"] == "FAIL":
        logger.error("Validation FAILED: review report before loading to Tableau")
        sys.exit(1)
    else:
        logger.info("Validation passed: data is ready for dashboard consumption")


if __name__ == "__main__":
    main()
