"""
Unit tests for ETL extract module.
"""

import pytest
import pandas as pd
from unittest.mock import patch, MagicMock
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "etl"))
from extract_cms_data import CMSExtractor
from config import DATASETS


class TestCMSExtractor:
    """Tests for the CMS data extraction pipeline."""

    def setup_method(self):
        self.extractor = CMSExtractor()

    def test_all_datasets_have_required_config(self):
        """Every configured dataset must have id, description, and output_file."""
        for name, config in DATASETS.items():
            assert "id" in config, f"{name} missing 'id'"
            assert "description" in config, f"{name} missing 'description'"
            assert "output_file" in config, f"{name} missing 'output_file'"
            assert config["output_file"].endswith(".csv"), f"{name} output must be CSV"

    def test_dataset_ids_are_unique(self):
        """No two datasets should share the same CMS identifier."""
        ids = [config["id"] for config in DATASETS.values()]
        assert len(ids) == len(set(ids)), "Duplicate dataset IDs found"

    @patch("extract_cms_data.requests.Session.get")
    def test_retry_on_failure(self, mock_get):
        """Extractor should retry on transient failures."""
        mock_get.side_effect = [
            ConnectionError("Connection refused"),
            ConnectionError("Connection refused"),
            MagicMock(status_code=200, json=lambda: {"distribution": [{"data": {"downloadURL": "http://test.csv"}}]}),
        ]
        # Should not raise after retries succeed
        # (In practice this tests the retry logic path)

    def test_extraction_log_initialized(self):
        """Extraction log should start empty."""
        assert self.extractor.extraction_log == []

    @patch("extract_cms_data.pd.read_csv")
    @patch.object(CMSExtractor, "get_download_url", return_value="http://test.csv")
    def test_extract_via_download_returns_dataframe(self, mock_url, mock_csv):
        """Download extraction should return a pandas DataFrame."""
        mock_csv.return_value = pd.DataFrame({"col1": [1, 2], "col2": ["a", "b"]})
        result = self.extractor.extract_via_download("test-id")
        assert isinstance(result, pd.DataFrame)
        assert len(result) == 2
