"""
Unit tests for data validation module.
"""

import pytest
import pandas as pd
import numpy as np
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "etl"))
from validate_data import DataValidator


class TestDataValidator:
    """Tests for the DataValidator class."""

    def setup_method(self):
        self.validator = DataValidator()

    def test_initial_status_is_pass(self):
        assert self.validator.results["overall_status"] == "PASS"

    def test_fail_propagates_to_overall(self):
        self.validator._record("test", "check1", "FAIL", "something broke")
        assert self.validator.results["overall_status"] == "FAIL"

    def test_warn_does_not_override_fail(self):
        self.validator._record("test", "check1", "FAIL", "broke")
        self.validator._record("test", "check2", "WARN", "meh")
        assert self.validator.results["datasets"]["test"]["status"] == "FAIL"

    def test_row_count_pass(self):
        df = pd.DataFrame({"a": range(100)})
        self.validator.check_row_count("test", df, 50)
        assert self.validator.results["datasets"]["test"]["checks"][0]["status"] == "PASS"

    def test_row_count_fail(self):
        df = pd.DataFrame({"a": range(10)})
        self.validator.check_row_count("test", df, 50)
        assert self.validator.results["datasets"]["test"]["checks"][0]["status"] == "FAIL"

    def test_null_rate_pass(self):
        df = pd.DataFrame({"a": [1, 2, 3, None], "b": [1, 2, 3, 4]})
        self.validator.check_null_rates("test", df, threshold=0.30)
        checks = self.validator.results["datasets"]["test"]["checks"]
        assert all(c["status"] == "PASS" for c in checks)

    def test_null_rate_warn(self):
        df = pd.DataFrame({"a": [1, None, None, None]})  # 75% null
        self.validator.check_null_rates("test", df, threshold=0.30)
        checks = self.validator.results["datasets"]["test"]["checks"]
        assert any(c["status"] == "WARN" for c in checks)

    def test_range_check_pass(self):
        df = pd.DataFrame({"score": [1.0, 2.5, 3.0, 4.5, 5.0]})
        self.validator.check_range("test", df, "score", 1, 5)
        assert self.validator.results["datasets"]["test"]["checks"][0]["status"] == "PASS"

    def test_range_check_warn(self):
        df = pd.DataFrame({"score": [0.5, 2.5, 6.0]})  # 0.5 and 6.0 out of [1,5]
        self.validator.check_range("test", df, "score", 1, 5)
        assert self.validator.results["datasets"]["test"]["checks"][0]["status"] == "WARN"

    def test_duplicate_check(self):
        df = pd.DataFrame({"id": [1, 2, 2, 3]})
        self.validator.check_duplicates("test", df, ["id"])
        assert self.validator.results["datasets"]["test"]["checks"][0]["status"] == "WARN"

    def test_referential_integrity_pass(self):
        child = pd.DataFrame({"fk": ["A", "B", "C"]})
        parent = pd.DataFrame({"pk": ["A", "B", "C", "D"]})
        self.validator.check_referential_integrity(
            "child", child, "fk", "parent", parent, "pk"
        )
        assert self.validator.results["datasets"]["child"]["checks"][0]["status"] == "PASS"
