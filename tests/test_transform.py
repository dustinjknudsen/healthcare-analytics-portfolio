"""
Unit tests for ETL transform module.
"""

import pytest
import pandas as pd
import numpy as np
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "etl"))
from transform_hospital_data import (
    standardize_columns,
    STATE_TO_REGION,
    OWNERSHIP_CATEGORIES,
)


class TestStandardizeColumns:
    """Tests for column name standardization."""

    def test_lowercase(self):
        df = pd.DataFrame({"Hospital Name": [1], "STATE": [2]})
        result = standardize_columns(df)
        assert list(result.columns) == ["hospital_name", "state"]

    def test_special_characters_replaced(self):
        df = pd.DataFrame({"Score (%)": [1], "Measure ID #": [2]})
        result = standardize_columns(df)
        for col in result.columns:
            assert " " not in col
            assert "(" not in col
            assert "#" not in col

    def test_multiple_underscores_collapsed(self):
        df = pd.DataFrame({"Excess  Readmission   Ratio": [1]})
        result = standardize_columns(df)
        assert "__" not in result.columns[0]


class TestStateMappings:
    """Tests for geographic reference data."""

    def test_all_50_states_mapped(self):
        states_50 = [
            "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
            "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
            "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
            "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
            "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
        ]
        for state in states_50:
            assert state in STATE_TO_REGION, f"{state} missing from region mapping"

    def test_regions_are_valid(self):
        valid_regions = {f"Region {i}" for i in range(1, 11)}
        for state, region in STATE_TO_REGION.items():
            assert region in valid_regions, f"{state} mapped to invalid region: {region}"

    def test_wa_is_region_10(self):
        """Dustin's state should be in Region 10 (Pacific Northwest)."""
        assert STATE_TO_REGION["WA"] == "Region 10"


class TestOwnershipCategories:
    """Tests for ownership type mappings."""

    def test_all_categories_have_simplified_form(self):
        valid_simplified = {"Government", "For-Profit", "Non-Profit", "Tribal", "Physician-Owned"}
        for raw, simplified in OWNERSHIP_CATEGORIES.items():
            assert simplified in valid_simplified, f"'{simplified}' not in valid categories"

    def test_proprietary_maps_to_forprofit(self):
        assert OWNERSHIP_CATEGORIES["Proprietary"] == "For-Profit"
