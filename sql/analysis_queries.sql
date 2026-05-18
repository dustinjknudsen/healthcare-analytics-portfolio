-- ============================================================================
-- Healthcare Analytics: SQL Analysis Queries
-- 
-- These queries run against the processed CMS hospital data and demonstrate
-- the analytical SQL used to support dashboard development.
-- Compatible with PostgreSQL / SQL Server / SQLite with minor adjustments.
-- ============================================================================


-- ============================================================================
-- 1. HOSPITAL QUALITY SCORECARD QUERIES
-- ============================================================================

-- Top 20 hospitals by star rating with readmission performance
-- Used in: Hospital Quality Scorecard dashboard, "Top Performers" view
SELECT
    facility_id,
    hospital_name,
    city,
    state,
    hospital_type,
    ownership_category,
    star_rating,
    avg_excess_readmission_ratio,
    readmission_rate,
    mspb_score,
    CASE
        WHEN star_rating >= 4 AND avg_excess_readmission_ratio < 1.0
            THEN 'High Quality / Low Readmissions'
        WHEN star_rating >= 4 AND avg_excess_readmission_ratio >= 1.0
            THEN 'High Quality / High Readmissions'
        WHEN star_rating < 3 AND avg_excess_readmission_ratio >= 1.0
            THEN 'Low Quality / High Readmissions'
        ELSE 'Mixed Performance'
    END AS performance_quadrant
FROM hospital_master
WHERE star_rating IS NOT NULL
ORDER BY star_rating DESC, avg_excess_readmission_ratio ASC
LIMIT 20;


-- Star rating distribution by ownership type
-- Used in: Hospital Quality Scorecard, "Ownership Analysis" tab
SELECT
    ownership_category,
    star_rating,
    COUNT(*) AS hospital_count,
    ROUND(
        COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (PARTITION BY ownership_category),
        1
    ) AS pct_of_ownership_type
FROM hospital_master
WHERE star_rating IS NOT NULL
    AND ownership_category IS NOT NULL
GROUP BY ownership_category, star_rating
ORDER BY ownership_category, star_rating;


-- Quality tier breakdown by HHS region
-- Used in: Geographic map overlay
SELECT
    hhs_region,
    quality_tier,
    COUNT(*) AS hospital_count,
    ROUND(AVG(readmission_rate) * 100, 2) AS avg_readmission_pct,
    ROUND(AVG(mspb_score), 4) AS avg_spending_ratio
FROM hospital_master
WHERE hhs_region IS NOT NULL
GROUP BY hhs_region, quality_tier
ORDER BY hhs_region, quality_tier;


-- ============================================================================
-- 2. READMISSIONS & PENALTIES ANALYSIS
-- ============================================================================

-- Penalty rate by state: what percentage of hospitals are penalized?
-- Used in: Readmissions dashboard, state choropleth map
SELECT
    state,
    COUNT(*) AS total_hospitals,
    SUM(CASE WHEN is_penalized = TRUE THEN 1 ELSE 0 END) AS penalized_count,
    ROUND(
        SUM(CASE WHEN is_penalized = TRUE THEN 1 ELSE 0 END) * 100.0 / COUNT(*),
        1
    ) AS penalty_rate_pct,
    ROUND(AVG(avg_excess_readmission_ratio), 4) AS avg_err,
    SUM(total_discharges) AS total_state_discharges
FROM hospital_master
WHERE is_penalized IS NOT NULL
GROUP BY state
ORDER BY penalty_rate_pct DESC;


-- Readmission patterns by diagnosis group
-- Used in: Readmissions dashboard, "By Condition" breakdown
SELECT
    measure_name,
    COUNT(DISTINCT facility_id) AS hospitals_reporting,
    ROUND(AVG(excess_readmission_ratio), 4) AS avg_err,
    ROUND(PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY excess_readmission_ratio), 4) AS p25_err,
    ROUND(PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY excess_readmission_ratio), 4) AS median_err,
    ROUND(PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY excess_readmission_ratio), 4) AS p75_err,
    SUM(number_of_readmissions) AS total_readmissions,
    SUM(number_of_discharges) AS total_discharges,
    ROUND(
        SUM(number_of_readmissions) * 100.0 / NULLIF(SUM(number_of_discharges), 0),
        2
    ) AS raw_readmission_rate_pct
FROM readmissions_detail
WHERE excess_readmission_ratio IS NOT NULL
GROUP BY measure_name
ORDER BY avg_err DESC;


-- Hospitals with consistently high readmissions across ALL diagnosis groups
-- Used in: Readmissions dashboard, "Chronic High Readmitters" alert table
SELECT
    r.facility_id,
    m.hospital_name,
    m.state,
    m.ownership_category,
    COUNT(*) AS conditions_reported,
    SUM(CASE WHEN r.excess_readmission_ratio > 1.0 THEN 1 ELSE 0 END) AS conditions_above_expected,
    ROUND(AVG(r.excess_readmission_ratio), 4) AS avg_err_all_conditions,
    ROUND(MAX(r.excess_readmission_ratio), 4) AS worst_err
FROM readmissions_detail r
JOIN hospital_master m ON r.facility_id = m.facility_id
WHERE r.excess_readmission_ratio IS NOT NULL
GROUP BY r.facility_id, m.hospital_name, m.state, m.ownership_category
HAVING COUNT(*) >= 4  -- reported at least 4 diagnosis groups
    AND SUM(CASE WHEN r.excess_readmission_ratio > 1.0 THEN 1 ELSE 0 END) = COUNT(*)
ORDER BY avg_err_all_conditions DESC
LIMIT 25;


-- ============================================================================
-- 3. COST ANALYSIS QUERIES
-- ============================================================================

-- Medicare spending efficiency by state
-- Used in: Cost Explorer dashboard, state comparison view
SELECT
    state,
    COUNT(*) AS hospitals,
    ROUND(AVG(mspb_score), 4) AS avg_mspb,
    ROUND(MIN(mspb_score), 4) AS min_mspb,
    ROUND(MAX(mspb_score), 4) AS max_mspb,
    SUM(CASE WHEN mspb_score > 1.0 THEN 1 ELSE 0 END) AS above_median_count,
    ROUND(
        SUM(CASE WHEN mspb_score > 1.0 THEN 1 ELSE 0 END) * 100.0 / COUNT(*),
        1
    ) AS pct_above_median
FROM hospital_master
WHERE mspb_score IS NOT NULL
GROUP BY state
ORDER BY avg_mspb DESC;


-- Cost vs Quality correlation: are higher-spending hospitals higher quality?
-- Used in: Cost Explorer dashboard, scatter plot
SELECT
    facility_id,
    hospital_name,
    state,
    star_rating,
    mspb_score,
    avg_excess_readmission_ratio,
    ownership_category,
    hospital_type,
    NTILE(4) OVER (ORDER BY mspb_score) AS spending_quartile,
    NTILE(4) OVER (ORDER BY star_rating DESC) AS quality_quartile
FROM hospital_master
WHERE star_rating IS NOT NULL
    AND mspb_score IS NOT NULL;


-- Spending quartile summary: do high spenders get better outcomes?
-- Used in: Cost Explorer dashboard, "Value Analysis" section
WITH quartiles AS (
    SELECT
        *,
        NTILE(4) OVER (ORDER BY mspb_score) AS spending_quartile
    FROM hospital_master
    WHERE mspb_score IS NOT NULL
)
SELECT
    spending_quartile,
    CASE spending_quartile
        WHEN 1 THEN 'Lowest Spending'
        WHEN 2 THEN 'Below Average'
        WHEN 3 THEN 'Above Average'
        WHEN 4 THEN 'Highest Spending'
    END AS quartile_label,
    COUNT(*) AS hospital_count,
    ROUND(AVG(mspb_score), 4) AS avg_mspb,
    ROUND(AVG(star_rating), 2) AS avg_star_rating,
    ROUND(AVG(avg_excess_readmission_ratio), 4) AS avg_err,
    ROUND(AVG(readmission_rate) * 100, 2) AS avg_readmission_pct
FROM quartiles
WHERE star_rating IS NOT NULL
GROUP BY spending_quartile
ORDER BY spending_quartile;


-- ============================================================================
-- 4. CROSS-CUTTING ANALYTICS
-- ============================================================================

-- Year-over-year penalty persistence (requires multi-year data)
-- Identifies hospitals that have been penalized across multiple reporting periods
-- Used in: Executive summary, "Chronic Underperformers" KPI

-- Ownership type performance summary
-- Used in: All dashboards, "Ownership Filter" dropdown context
SELECT
    ownership_category,
    COUNT(*) AS hospitals,
    ROUND(AVG(star_rating), 2) AS avg_stars,
    ROUND(AVG(mspb_score), 4) AS avg_spending,
    ROUND(AVG(avg_excess_readmission_ratio), 4) AS avg_readmission_ratio,
    ROUND(SUM(CASE WHEN is_penalized THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 1) AS penalty_rate,
    SUM(total_discharges) AS total_discharges
FROM hospital_master
WHERE ownership_category IS NOT NULL
GROUP BY ownership_category
ORDER BY avg_stars DESC;
