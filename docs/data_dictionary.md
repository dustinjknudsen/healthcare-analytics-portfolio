# Data Dictionary

## Processed Datasets

### `hospital_master.csv`
Hospital-level dataset joining demographics, quality ratings, readmission metrics, and spending efficiency. Primary dataset for all dashboards.

| Column | Type | Description |
|--------|------|-------------|
| `facility_id` | str | CMS Certification Number (CCN), 6-character unique hospital identifier |
| `hospital_name` | str | Official hospital name |
| `address` | str | Street address |
| `city` | str | City |
| `state` | str | 2-letter state abbreviation |
| `zip_code` | str | 5-digit ZIP code |
| `county_name` | str | County name |
| `hospital_type` | str | Acute Care, Critical Access, Psychiatric, etc. |
| `hospital_ownership` | str | Full ownership description from CMS |
| `ownership_category` | str | Simplified: Government, For-Profit, Non-Profit, Tribal |
| `hhs_region` | str | HHS Region 1-10 |
| `has_emergency` | bool | Whether hospital has emergency services |
| `star_rating` | float | CMS Overall Hospital Quality Star Rating (1-5), null if not rated |
| `avg_excess_readmission_ratio` | float | Mean ERR across all reported diagnosis groups. >1.0 = more readmissions than expected |
| `max_excess_readmission_ratio` | float | Worst ERR across diagnosis groups |
| `total_discharges` | float | Total discharges across all HRRP diagnosis groups |
| `total_readmissions` | float | Total readmissions across all HRRP diagnosis groups |
| `diagnosis_groups_reported` | int | Number of HRRP conditions reported (max 6) |
| `is_penalized` | bool | Whether hospital has ANY excess readmission ratio > 1.0 |
| `mspb_score` | float | Medicare Spending Per Beneficiary ratio. >1.0 = above national median |
| `above_national_median` | bool | Whether MSPB score exceeds 1.0 |
| `readmission_rate` | float | Computed: total_readmissions / total_discharges |
| `quality_tier` | str | Derived from star_rating: Below Average, Average, Above Average, Excellent |

### `readmissions_detail.csv`
Facility × diagnosis group level readmission data from the Hospital Readmissions Reduction Program (HRRP).

| Column | Type | Description |
|--------|------|-------------|
| `facility_id` | str | CCN linking to hospital_master |
| `hospital_name` | str | Hospital name |
| `state` | str | State |
| `measure_name` | str | Diagnosis group (e.g., AMI, HF, PN, COPD, THA/TKA, CABG) |
| `excess_readmission_ratio` | float | Predicted / Expected readmission ratio. >1.0 = excess readmissions |
| `predicted_readmission_rate` | float | Model-predicted readmission rate for this hospital |
| `expected_readmission_rate` | float | Expected rate based on case mix |
| `number_of_readmissions` | float | Count of 30-day readmissions |
| `number_of_discharges` | float | Count of index admissions |
| `has_excess_readmissions` | bool | ERR > 1.0 |
| `is_penalized` | bool | Hospital-level penalty flag (any condition > 1.0) |

### `state_summary.csv`
State-level aggregation of hospital quality and cost metrics.

| Column | Type | Description |
|--------|------|-------------|
| `state` | str | 2-letter state abbreviation |
| `hospital_count` | int | Number of hospitals in state |
| `avg_star_rating` | float | Mean star rating |
| `median_star_rating` | float | Median star rating |
| `pct_penalized` | float | Fraction of hospitals with readmission penalties |
| `avg_readmission_rate` | float | Mean readmission rate |
| `avg_mspb_score` | float | Mean Medicare spending ratio |
| `total_discharges` | float | Total discharges statewide |
| `pct_nonprofit` | float | Fraction of hospitals that are non-profit |
| `pct_forprofit` | float | Fraction that are for-profit |
| `pct_government` | float | Fraction that are government-owned |
| `hhs_region` | str | HHS Region |

## Data Sources

All data from [CMS Provider Data Catalog](https://data.cms.gov/provider-data/), public domain, no PHI.

| Source Dataset | CMS ID | Update Frequency |
|----------------|--------|-----------------|
| Hospital General Information | `xubh-q36u` | Quarterly |
| Hospital Readmissions Reduction Program | `9n3s-kdb3` | Annually |
| Timely and Effective Care | `yv7e-xc69` | Quarterly |
| Medicare Spending Per Beneficiary | `rrqw-56er` | Annually |
| Complications and Deaths | `ynj2-r877` | Quarterly |

## HRRP Diagnosis Groups

| Code | Condition |
|------|-----------|
| AMI | Acute Myocardial Infarction |
| HF | Heart Failure |
| PN | Pneumonia |
| COPD | Chronic Obstructive Pulmonary Disease |
| THA/TKA | Total Hip/Knee Arthroplasty |
| CABG | Coronary Artery Bypass Graft |
