-- Each query returns the number of records that violate one business rule.
-- A successful input dataset returns zero failures for every check.

DROP VIEW IF EXISTS vw_sql_data_quality_results;

CREATE VIEW vw_sql_data_quality_results AS
SELECT
    'Q01' AS test_id,
    'Duplicate ICP IDs' AS test_name,
    COUNT(*) AS failure_count
FROM (
    SELECT icp_id
    FROM icp_master
    GROUP BY icp_id
    HAVING COUNT(*) > 1
)

UNION ALL

SELECT
    'Q02',
    'Duplicate consumption IDs',
    COUNT(*)
FROM (
    SELECT consumption_id
    FROM monthly_consumption
    GROUP BY consumption_id
    HAVING COUNT(*) > 1
)

UNION ALL

SELECT
    'Q03',
    'Consumption rows without ICP master data',
    COUNT(*)
FROM monthly_consumption AS c
LEFT JOIN icp_master AS i ON c.icp_id = i.icp_id
WHERE i.icp_id IS NULL

UNION ALL

SELECT
    'Q04',
    'ICP rows without retailer master data',
    COUNT(*)
FROM icp_master AS i
LEFT JOIN retailer_master AS r ON i.retailer_id = r.retailer_id
WHERE r.retailer_id IS NULL

UNION ALL

SELECT
    'Q05',
    'Negative time-band consumption values',
    COUNT(*)
FROM monthly_consumption
WHERE weekend_kwh < 0
   OR peak_kwh < 0
   OR shoulder_kwh < 0
   OR off_peak_kwh < 0
   OR super_off_peak_kwh < 0

UNION ALL

SELECT
    'Q06',
    'Time-band quantities not reconciling to total kWh',
    COUNT(*)
FROM monthly_consumption
WHERE ABS(
    weekend_kwh + peak_kwh + shoulder_kwh + off_peak_kwh
    + super_off_peak_kwh - total_kwh
) > 0.001

UNION ALL

SELECT
    'Q07',
    'Expected billing rows without six price components',
    COUNT(*)
FROM vw_expected_billing_summary_sql
WHERE component_count <> 6;
