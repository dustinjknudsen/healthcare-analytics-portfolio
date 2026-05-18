"""
Configuration for CMS Provider Data Catalog ETL pipeline.
API docs: https://data.cms.gov/provider-data/
"""

import os
from pathlib import Path

# --- Project Paths ---
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
SAMPLE_DIR = DATA_DIR / "sample"

# Create directories if they don't exist
for d in [RAW_DIR, PROCESSED_DIR, SAMPLE_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# --- CMS Provider Data Catalog API ---
CMS_BASE_URL = "https://data.cms.gov/provider-data"
CMS_API_BASE = f"{CMS_BASE_URL}/api/1"
CMS_METASTORE_URL = f"{CMS_API_BASE}/metastore/schemas/dataset/items"
CMS_DATASTORE_URL = f"{CMS_API_BASE}/datastore/sql"

# Dataset identifiers (from CMS Provider Data Catalog)
DATASETS = {
    "hospital_general_info": {
        "id": "xubh-q36u",
        "description": "Hospital General Information: demographics, location, ownership, star ratings",
        "output_file": "hospital_general_info.csv",
    },
    "readmissions": {
        "id": "9n3s-kdb3",
        "description": "Hospital Readmissions Reduction Program: excess readmission ratios, penalties",
        "output_file": "readmissions.csv",
    },
    "timely_effective_care": {
        "id": "yv7e-xc69",
        "description": "Timely and Effective Care: quality measures (ED wait times, immunization, etc.)",
        "output_file": "timely_effective_care.csv",
    },
    "medicare_spending": {
        "id": "rrqw-56er",
        "description": "Medicare Spending Per Beneficiary: hospital-level cost data",
        "output_file": "medicare_spending.csv",
    },
    "complications_deaths": {
        "id": "ynj2-r877",
        "description": "Complications and Deaths: patient safety indicators, mortality rates",
        "output_file": "complications_deaths.csv",
    },
}

# --- API Settings ---
API_PAGE_SIZE = 500          # CMS API max rows per request
API_MAX_RETRIES = 3          # Retry attempts on failure
API_RETRY_DELAY = 2          # Base delay in seconds (exponential backoff)
API_TIMEOUT = 30             # Request timeout in seconds
API_REQUEST_DELAY = 0.5      # Delay between paginated requests (be nice to CMS)

# --- Data Quality Thresholds ---
NULL_THRESHOLD = 0.30        # Max allowable null fraction per column
DUPLICATE_THRESHOLD = 0.01   # Max allowable duplicate fraction
MIN_ROW_COUNT = {
    "hospital_general_info": 4000,
    "readmissions": 10000,
    "timely_effective_care": 50000,
    "medicare_spending": 3000,
    "complications_deaths": 10000,
}

# --- Logging ---
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
