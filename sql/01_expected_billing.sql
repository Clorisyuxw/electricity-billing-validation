-- Expected billing calculated independently in SQL.
-- Source tables are loaded from the reference and simulated CSV files by
-- scripts/09_validate_sql_workflow.py.

DROP VIEW IF EXISTS vw_expected_billing_detail_sql;

CREATE VIEW vw_expected_billing_detail_sql AS
WITH charge_quantities AS (
    -- Fixed charges use inclusive connection days.
    SELECT
        c.consumption_id,
        c.icp_id,
        c.billing_month,
        c.billing_period_start,
        c.billing_period_end,
        c.icp_days,
        'Fixed Daily Charge' AS component_name,
        CAST(c.icp_days AS REAL) AS quantity,
        'connection days' AS quantity_unit
    FROM monthly_consumption AS c

    UNION ALL

    SELECT consumption_id, icp_id, billing_month, billing_period_start,
           billing_period_end, icp_days, 'Weekend', weekend_kwh, 'kWh'
    FROM monthly_consumption

    UNION ALL

    SELECT consumption_id, icp_id, billing_month, billing_period_start,
           billing_period_end, icp_days, 'Peak', peak_kwh, 'kWh'
    FROM monthly_consumption

    UNION ALL

    SELECT consumption_id, icp_id, billing_month, billing_period_start,
           billing_period_end, icp_days, 'Shoulder', shoulder_kwh, 'kWh'
    FROM monthly_consumption

    UNION ALL

    SELECT consumption_id, icp_id, billing_month, billing_period_start,
           billing_period_end, icp_days, 'Off Peak', off_peak_kwh, 'kWh'
    FROM monthly_consumption

    UNION ALL

    SELECT consumption_id, icp_id, billing_month, billing_period_start,
           billing_period_end, icp_days, 'Super Off Peak',
           super_off_peak_kwh, 'kWh'
    FROM monthly_consumption
)
SELECT
    q.consumption_id,
    q.icp_id,
    i.retailer_id,
    i.price_category_code,
    i.region,
    q.billing_month,
    q.billing_period_start,
    q.billing_period_end,
    q.icp_days,
    p.price_year,
    q.component_name,
    p.component_code,
    q.quantity,
    q.quantity_unit,
    p.delivery_price,
    p.unit AS price_unit,
    q.quantity * p.delivery_price AS expected_charge_unrounded
FROM charge_quantities AS q
INNER JOIN icp_master AS i
    ON q.icp_id = i.icp_id
INNER JOIN price_schedule_all AS p
    ON i.price_category_code = p.price_category_code
   AND q.component_name = p.component_name
   -- ISO dates sort chronologically as text in SQLite.
   AND p.effective_from <= q.billing_period_start
   AND (p.effective_to IS NULL OR p.effective_to >= q.billing_period_end);


DROP VIEW IF EXISTS vw_expected_billing_summary_sql;

CREATE VIEW vw_expected_billing_summary_sql AS
SELECT
    consumption_id,
    icp_id,
    retailer_id,
    price_category_code,
    region,
    billing_month,
    billing_period_start,
    billing_period_end,
    icp_days,
    price_year,
    COUNT(*) AS component_count,
    SUM(expected_charge_unrounded) AS expected_delivery_charge_unrounded,
    ROUND(SUM(expected_charge_unrounded), 2) AS expected_delivery_charge
FROM vw_expected_billing_detail_sql
GROUP BY
    consumption_id,
    icp_id,
    retailer_id,
    price_category_code,
    region,
    billing_month,
    billing_period_start,
    billing_period_end,
    icp_days,
    price_year;
