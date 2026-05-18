"""
Transform and enrich CMS hospital data for dashboard consumption.

Takes raw CSV extracts from extract_cms_data.py and produces analysis-ready
datasets with:
  - Standardized column names and data types
  - Joined hospital demographics with quality/cost/readmission metrics
  - Computed fields: penalty rates, quality composites, regional aggregations
  - State and region-level summary tables

Usage:
    python etl/transform_hospital_data.py
"""

import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from config import RAW_DIR, PROCESSED_DIR, LOG_LEVEL, LOG_FORMAT

logging.basicConfig(level=LOG_LEVEL, format=LOG_FORMAT)
logger = logging.getLogger("transform")

# HHS Region mapping (used by CMS for geographic analysis)
STATE_TO_REGION = {
    "CT": "Region 1", "ME": "Region 1", "MA": "Region 1", "NH": "Region 1",
    "RI": "Region 1", "VT": "Region 1",
    "NJ": "Region 2", "NY": "Region 2", "PR": "Region 2", "VI": "Region 2",
    "DE": "Region 3", "DC": "Region 3", "MD": "Region 3", "PA": "Region 3",
    "VA": "Region 3", "WV": "Region 3",
    "AL": "Region 4", "FL": "Region 4", "GA": "Region 4", "KY": "Region 4",
    "MS": "Region 4", "NC": "Region 4", "SC": "Region 4", "TN": "Region 4",
    "IL": "Region 5", "IN": "Region 5", "MI": "Region 5", "MN": "Region 5",
    "OH": "Region 5", "WI": "Region 5",
    "AR": "Region 6", "LA": "Region 6", "NM": "Region 6", "OK": "Region 6",
    "TX": "Region 6",
    "IA": "Region 7", "KS": "Region 7", "MO": "Region 7", "NE": "Region 7",
    "CO": "Region 8", "MT": "Region 8", "ND": "Region 8", "SD": "Region 8",
    "UT": "Region 8", "WY": "Region 8",
    "AZ": "Region 9", "CA": "Region 9", "HI": "Region 9", "NV": "Region 9",
    "GU": "Region 9", "AS": "Region 9",
    "AK": "Region 10", "ID": "Region 10", "OR": "Region 10", "WA": "Region 10",
}

OWNERSHIP_CATEGORIES = {
    "Government - Federal": "Government",
    "Government - Hospital District or Authority": "Government",
    "Government - Local": "Government",
    "Government - State": "Government",
    "Proprietary": "For-Profit",
    "Voluntary non-profit - Church": "Non-Profit",
    "Voluntary non-profit - Other": "Non-Profit",
    "Voluntary non-profit - Private": "Non-Profit",
    "Tribal": "Tribal",
    "Physician": "Physician-Owned",
}


def standardize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Lowercase column names, replace spaces with underscores."""
    df.columns = (
        df.columns.str.lower()
        .str.replace(r"[^\w]", "_", regex=True)
        .str.replace(r"_+", "_", regex=True)
        .str.strip("_")
    )
    return df


def transform_hospital_general(raw_path: Path) -> pd.DataFrame:
    """
    Transform Hospital General Information dataset.
    
    Key fields: facility_id (CCN), hospital_name, state, hospital_type,
    ownership, star_rating, emergency_services, geocoded location.
    """
    logger.info("Transforming: Hospital General Information")
    df = pd.read_csv(raw_path, low_memory=False, dtype={"Facility ID": str})
    df = standardize_columns(df)

    # Standardize facility ID (CMS Certification Number): always 6 chars
    if "facility_id" in df.columns:
        df["facility_id"] = df["facility_id"].astype(str).str.zfill(6)

    # Parse star rating to numeric (some are "Not Available")
    if "hospital_overall_rating" in df.columns:
        df["star_rating"] = pd.to_numeric(
            df["hospital_overall_rating"], errors="coerce"
        )

    # Map ownership to simplified categories
    if "hospital_ownership" in df.columns:
        df["ownership_category"] = df["hospital_ownership"].map(OWNERSHIP_CATEGORIES)

    # Add HHS region
    if "state" in df.columns:
        df["hhs_region"] = df["state"].map(STATE_TO_REGION)

    # Parse emergency services to boolean
    if "emergency_services" in df.columns:
        df["has_emergency"] = df["emergency_services"].str.lower() == "yes"

    # Select and rename key columns
    keep_cols = [
        "facility_id", "hospital_name", "address", "city", "state", "zip_code",
        "county_name", "phone_number", "hospital_type", "hospital_ownership",
        "ownership_category", "hhs_region", "has_emergency", "star_rating",
    ]
    available = [c for c in keep_cols if c in df.columns]
    df = df[available].copy()

    logger.info(f"  → {len(df):,} hospitals, {df['star_rating'].notna().sum():,} with star ratings")
    return df


def transform_readmissions(raw_path: Path) -> pd.DataFrame:
    """
    Transform Hospital Readmissions Reduction Program data.

    Computes excess readmission ratios, penalty indicators, and
    aggregates by diagnosis group.
    """
    logger.info("Transforming: Readmissions Reduction Program")
    df = pd.read_csv(raw_path, low_memory=False, dtype={"Facility ID": str})
    df = standardize_columns(df)

    if "facility_id" in df.columns:
        df["facility_id"] = df["facility_id"].astype(str).str.zfill(6)

    # Parse numeric measures (CMS uses "Not Available" for suppressed data)
    numeric_cols = [
        "excess_readmission_ratio", "predicted_readmission_rate",
        "expected_readmission_rate", "number_of_readmissions",
        "number_of_discharges",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Flag hospitals with excess readmissions (ratio > 1.0)
    if "excess_readmission_ratio" in df.columns:
        df["has_excess_readmissions"] = df["excess_readmission_ratio"] > 1.0

    # Compute readmission penalty indicator per hospital
    # A hospital is penalized if ANY of its diagnosis groups has ERR > 1.0
    if "excess_readmission_ratio" in df.columns and "facility_id" in df.columns:
        penalized = (
            df.groupby("facility_id")["has_excess_readmissions"]
            .any()
            .reset_index()
            .rename(columns={"has_excess_readmissions": "is_penalized"})
        )
        df = df.merge(penalized, on="facility_id", how="left")

    logger.info(f"  → {len(df):,} readmission records across {df['facility_id'].nunique():,} hospitals")
    return df


def transform_timely_effective_care(raw_path: Path) -> pd.DataFrame:
    """
    Transform Timely and Effective Care measures.
    
    Focuses on key measures: ED wait times (OP-18, OP-22),
    immunization rates, sepsis bundle compliance.
    """
    logger.info("Transforming: Timely and Effective Care")
    df = pd.read_csv(raw_path, low_memory=False, dtype={"Facility ID": str})
    df = standardize_columns(df)

    if "facility_id" in df.columns:
        df["facility_id"] = df["facility_id"].astype(str).str.zfill(6)

    # Parse the score field to numeric
    if "score" in df.columns:
        df["score_numeric"] = pd.to_numeric(df["score"], errors="coerce")

    # Key measures of interest for dashboards
    key_measures = {
        "OP_18b": "ED Wait Time (median minutes)",
        "OP_22": "ED Left Without Being Seen (%)",
        "IMM_3": "Healthcare Workers Influenza Vaccination (%)",
        "SEP_1": "Sepsis Bundle Compliance (%)",
        "OP_23": "ED Head CT Results Within 45 Minutes (%)",
        "EDV": "Emergency Department Volume",
    }

    if "measure_id" in df.columns:
        df["measure_description"] = df["measure_id"].map(key_measures)
        df["is_key_measure"] = df["measure_id"].isin(key_measures.keys())

    logger.info(f"  → {len(df):,} measure records, {df['facility_id'].nunique():,} hospitals")
    return df


def transform_medicare_spending(raw_path: Path) -> pd.DataFrame:
    """
    Transform Medicare Spending Per Beneficiary data.
    
    MSPB measures hospital-level spending efficiency relative
    to the national median.
    """
    logger.info("Transforming: Medicare Spending Per Beneficiary")
    df = pd.read_csv(raw_path, low_memory=False, dtype={"Facility ID": str})
    df = standardize_columns(df)

    if "facility_id" in df.columns:
        df["facility_id"] = df["facility_id"].astype(str).str.zfill(6)

    if "score" in df.columns:
        df["mspb_score"] = pd.to_numeric(df["score"], errors="coerce")
        # MSPB > 1.0 means hospital spends MORE than national median
        df["above_national_median"] = df["mspb_score"] > 1.0

    logger.info(f"  → {len(df):,} spending records")
    return df


def build_hospital_master(
    hospitals: pd.DataFrame,
    readmissions: pd.DataFrame,
    spending: pd.DataFrame,
) -> pd.DataFrame:
    """
    Build a master hospital-level dataset joining demographics,
    readmission penalties, and spending efficiency.
    
    This is the primary dataset for the Tableau Hospital Quality Scorecard.
    """
    logger.info("Building master hospital dataset...")

    # Aggregate readmissions to hospital level
    readmit_agg = (
        readmissions.groupby("facility_id")
        .agg(
            avg_excess_readmission_ratio=("excess_readmission_ratio", "mean"),
            max_excess_readmission_ratio=("excess_readmission_ratio", "max"),
            total_discharges=("number_of_discharges", "sum"),
            total_readmissions=("number_of_readmissions", "sum"),
            diagnosis_groups_reported=("facility_id", "count"),
            is_penalized=("is_penalized", "first"),
        )
        .reset_index()
    )

    # Get MSPB score per hospital (should be 1 row per hospital)
    spend_agg = spending[["facility_id", "mspb_score", "above_national_median"]].copy()
    spend_agg = spend_agg.drop_duplicates(subset="facility_id", keep="first")

    # Join everything
    master = hospitals.merge(readmit_agg, on="facility_id", how="left")
    master = master.merge(spend_agg, on="facility_id", how="left")

    # Compute overall readmission rate
    master["readmission_rate"] = (
        master["total_readmissions"] / master["total_discharges"]
    ).round(4)

    # Quality tier based on star rating
    master["quality_tier"] = pd.cut(
        master["star_rating"],
        bins=[0, 2, 3, 4, 5],
        labels=["Below Average", "Average", "Above Average", "Excellent"],
        include_lowest=True,
    )

    logger.info(
        f"  → Master dataset: {len(master):,} hospitals, "
        f"{len(master.columns)} columns"
    )
    return master


def build_state_summary(master: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate hospital master data to state level for geographic dashboards.
    """
    logger.info("Building state-level summary...")

    state_summary = (
        master.groupby("state")
        .agg(
            hospital_count=("facility_id", "count"),
            avg_star_rating=("star_rating", "mean"),
            median_star_rating=("star_rating", "median"),
            pct_penalized=("is_penalized", "mean"),
            avg_readmission_rate=("readmission_rate", "mean"),
            avg_mspb_score=("mspb_score", "mean"),
            total_discharges=("total_discharges", "sum"),
            pct_nonprofit=("ownership_category", lambda x: (x == "Non-Profit").mean()),
            pct_forprofit=("ownership_category", lambda x: (x == "For-Profit").mean()),
            pct_government=("ownership_category", lambda x: (x == "Government").mean()),
        )
        .reset_index()
    )

    # Round percentages
    pct_cols = [c for c in state_summary.columns if c.startswith("pct_")]
    state_summary[pct_cols] = state_summary[pct_cols].round(4)
    state_summary["avg_star_rating"] = state_summary["avg_star_rating"].round(2)
    state_summary["avg_mspb_score"] = state_summary["avg_mspb_score"].round(4)

    # Add HHS region
    state_summary["hhs_region"] = state_summary["state"].map(STATE_TO_REGION)

    logger.info(f"  → {len(state_summary)} states/territories")
    return state_summary


def main():
    logger.info("=" * 60)
    logger.info("TRANSFORM PIPELINE START")
    logger.info("=" * 60)

    # Check for raw files
    raw_files = {
        "hospital_general_info": RAW_DIR / "hospital_general_info.csv",
        "readmissions": RAW_DIR / "readmissions.csv",
        "timely_effective_care": RAW_DIR / "timely_effective_care.csv",
        "medicare_spending": RAW_DIR / "medicare_spending.csv",
    }

    missing = [k for k, v in raw_files.items() if not v.exists()]
    if missing:
        logger.error(
            f"Missing raw files: {missing}. Run extract_cms_data.py first."
        )
        sys.exit(1)

    # Transform individual datasets
    hospitals = transform_hospital_general(raw_files["hospital_general_info"])
    readmissions = transform_readmissions(raw_files["readmissions"])
    timely_care = transform_timely_effective_care(raw_files["timely_effective_care"])
    spending = transform_medicare_spending(raw_files["medicare_spending"])

    # Build derived datasets
    master = build_hospital_master(hospitals, readmissions, spending)
    state_summary = build_state_summary(master)

    # Save processed outputs
    outputs = {
        "hospital_master.csv": master,
        "readmissions_detail.csv": readmissions,
        "timely_effective_care.csv": timely_care,
        "state_summary.csv": state_summary,
    }

    for filename, df in outputs.items():
        output_path = PROCESSED_DIR / filename
        df.to_csv(output_path, index=False)
        logger.info(f"Saved: {output_path.name} ({len(df):,} rows)")

    logger.info("=" * 60)
    logger.info("TRANSFORM PIPELINE COMPLETE")
    logger.info(f"Output directory: {PROCESSED_DIR}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
