"""
Extract data from CMS Provider Data Catalog REST API.

Usage:
    python etl/extract_cms_data.py                  # Extract all datasets
    python etl/extract_cms_data.py --dataset readmissions  # Extract one dataset

The CMS Provider Data Catalog exposes a DKAN-based API. Each dataset has a UUID
that maps to a metastore entry, which contains the downloadURL for the full CSV.
For larger datasets, we use the datastore SQL endpoint with LIMIT/OFFSET pagination.
"""

import argparse
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

import requests
import pandas as pd

# Add parent to path for config import
sys.path.insert(0, str(Path(__file__).parent))
from config import (
    DATASETS,
    RAW_DIR,
    CMS_METASTORE_URL,
    CMS_DATASTORE_URL,
    API_PAGE_SIZE,
    API_MAX_RETRIES,
    API_RETRY_DELAY,
    API_TIMEOUT,
    API_REQUEST_DELAY,
    LOG_LEVEL,
    LOG_FORMAT,
)

logging.basicConfig(level=LOG_LEVEL, format=LOG_FORMAT)
logger = logging.getLogger("extract")


class CMSExtractor:
    """Handles extraction from CMS Provider Data Catalog API."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "HealthcareAnalyticsPortfolio/1.0",
            "Accept": "application/json",
        })
        self.extraction_log = []

    def _request_with_retry(self, url: str, params: dict = None) -> requests.Response:
        """Make HTTP request with exponential backoff retry."""
        for attempt in range(API_MAX_RETRIES):
            try:
                response = self.session.get(url, params=params, timeout=API_TIMEOUT)
                response.raise_for_status()
                return response
            except requests.exceptions.RequestException as e:
                wait_time = API_RETRY_DELAY * (2 ** attempt)
                logger.warning(
                    f"Request failed (attempt {attempt + 1}/{API_MAX_RETRIES}): {e}. "
                    f"Retrying in {wait_time}s..."
                )
                if attempt < API_MAX_RETRIES - 1:
                    time.sleep(wait_time)
                else:
                    raise

    def get_download_url(self, dataset_id: str) -> str:
        """Retrieve the CSV download URL from dataset metadata."""
        url = f"{CMS_METASTORE_URL}/{dataset_id}?show-reference-ids=false"
        logger.info(f"Fetching metadata for dataset: {dataset_id}")
        response = self._request_with_retry(url)
        metadata = response.json()
        download_url = metadata["distribution"][0]["data"]["downloadURL"]
        logger.info(f"Download URL resolved: {download_url}")
        return download_url

    def extract_via_download(self, dataset_id: str) -> pd.DataFrame:
        """Extract dataset by downloading the full CSV (preferred for smaller datasets)."""
        download_url = self.get_download_url(dataset_id)
        logger.info(f"Downloading full CSV from: {download_url}")
        df = pd.read_csv(download_url, low_memory=False)
        logger.info(f"Downloaded {len(df):,} rows, {len(df.columns)} columns")
        return df

    def extract_via_sql_api(self, resource_id: str) -> pd.DataFrame:
        """
        Extract dataset using the datastore SQL endpoint with pagination.
        Used for larger datasets that may timeout on full download.
        
        The CMS datastore SQL API accepts queries like:
            SELECT * FROM {resource_id} LIMIT 500 OFFSET 0
        """
        all_rows = []
        offset = 0
        page = 1

        while True:
            query = f"[SELECT * FROM {resource_id}][LIMIT {API_PAGE_SIZE} OFFSET {offset}]"
            url = f"{CMS_DATASTORE_URL}?query={query}"

            logger.info(f"Fetching page {page} (offset={offset}, limit={API_PAGE_SIZE})")
            response = self._request_with_retry(url)
            data = response.json()

            if not data:
                logger.info(f"No more data at offset {offset}. Extraction complete.")
                break

            all_rows.extend(data)
            logger.info(f"Page {page}: retrieved {len(data)} rows (total: {len(all_rows):,})")

            if len(data) < API_PAGE_SIZE:
                break

            offset += API_PAGE_SIZE
            page += 1
            time.sleep(API_REQUEST_DELAY)  # Rate limiting

        df = pd.DataFrame(all_rows)
        logger.info(f"SQL API extraction complete: {len(df):,} total rows")
        return df

    def extract_dataset(self, name: str, dataset_config: dict) -> pd.DataFrame:
        """Extract a single dataset and save to raw directory."""
        dataset_id = dataset_config["id"]
        output_file = RAW_DIR / dataset_config["output_file"]

        logger.info(f"{'='*60}")
        logger.info(f"Extracting: {name}")
        logger.info(f"Description: {dataset_config['description']}")
        logger.info(f"Dataset ID: {dataset_id}")
        logger.info(f"{'='*60}")

        start_time = time.time()

        try:
            # Use direct download: simpler and works for all CMS datasets
            df = self.extract_via_download(dataset_id)

            # Save raw extract
            df.to_csv(output_file, index=False)
            elapsed = time.time() - start_time

            log_entry = {
                "dataset": name,
                "dataset_id": dataset_id,
                "rows": len(df),
                "columns": len(df.columns),
                "output_file": str(output_file),
                "elapsed_seconds": round(elapsed, 2),
                "timestamp": datetime.utcnow().isoformat(),
                "status": "success",
            }
            self.extraction_log.append(log_entry)

            logger.info(
                f"✓ {name}: {len(df):,} rows → {output_file.name} "
                f"({elapsed:.1f}s)"
            )
            return df

        except Exception as e:
            elapsed = time.time() - start_time
            log_entry = {
                "dataset": name,
                "dataset_id": dataset_id,
                "error": str(e),
                "elapsed_seconds": round(elapsed, 2),
                "timestamp": datetime.utcnow().isoformat(),
                "status": "failed",
            }
            self.extraction_log.append(log_entry)
            logger.error(f"✗ {name}: extraction failed: {e}")
            raise

    def extract_all(self) -> dict[str, pd.DataFrame]:
        """Extract all configured datasets."""
        results = {}
        for name, config in DATASETS.items():
            try:
                results[name] = self.extract_dataset(name, config)
            except Exception:
                logger.error(f"Skipping {name} due to extraction failure")
                continue
        return results

    def print_summary(self):
        """Print extraction summary."""
        logger.info(f"\n{'='*60}")
        logger.info("EXTRACTION SUMMARY")
        logger.info(f"{'='*60}")
        for entry in self.extraction_log:
            status = "✓" if entry["status"] == "success" else "✗"
            if entry["status"] == "success":
                logger.info(
                    f"  {status} {entry['dataset']}: {entry['rows']:,} rows "
                    f"({entry['elapsed_seconds']}s)"
                )
            else:
                logger.info(f"  {status} {entry['dataset']}: FAILED: {entry['error']}")
        logger.info(f"{'='*60}")


def main():
    parser = argparse.ArgumentParser(description="Extract CMS Provider Data Catalog datasets")
    parser.add_argument(
        "--dataset",
        choices=list(DATASETS.keys()),
        help="Extract a specific dataset (default: all)",
    )
    args = parser.parse_args()

    extractor = CMSExtractor()

    if args.dataset:
        config = DATASETS[args.dataset]
        extractor.extract_dataset(args.dataset, config)
    else:
        extractor.extract_all()

    extractor.print_summary()


if __name__ == "__main__":
    main()
