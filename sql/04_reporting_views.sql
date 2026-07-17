-- Reporting views use the same one-cent materiality threshold as the
-- reconciliation process.

DROP VIEW IF EXISTS vw_monthly_revenue_performance_sql;

CREATE VIEW vw_monthly_revenue_performance_sql AS
SELECT
    billing_month,
    price_year,
    COUNT(*) AS bill_count,
    ROUND(SUM(expected_delivery_charge_unrounded), 2) AS expected_revenue,
    ROUND(SUM(system_billed_amount_unrounded), 2) AS system_billed_revenue,
    ROUND(SUM(
        CASE WHEN ABS(billing_variance_unrounded) > 0.01
             THEN billing_variance_unrounded ELSE 0 END
    ), 2) AS net_billing_variance,
    ROUND(SUM(
        CASE WHEN ABS(billing_variance_unrounded) > 0.01
             THEN ABS(billing_variance_unrounded) ELSE 0 END
    ), 2) AS total_absolute_variance,
    SUM(CASE WHEN validation_status = 'REVIEW' THEN 1 ELSE 0 END) AS exception_count,
    ROUND(
        100.0 * SUM(CASE WHEN validation_status = 'PASS' THEN 1 ELSE 0 END)
        / COUNT(*),
        2
    ) AS billing_accuracy_rate_pct
FROM vw_billing_reconciliation_sql
GROUP BY billing_month, price_year;


DROP VIEW IF EXISTS vw_retailer_revenue_performance_sql;

CREATE VIEW vw_retailer_revenue_performance_sql AS
SELECT
    retailer_id,
    COUNT(*) AS bill_count,
    ROUND(SUM(expected_delivery_charge_unrounded), 2) AS expected_revenue,
    ROUND(SUM(system_billed_amount_unrounded), 2) AS system_billed_revenue,
    SUM(CASE WHEN validation_status = 'REVIEW' THEN 1 ELSE 0 END) AS exception_count,
    ROUND(SUM(
        CASE WHEN ABS(billing_variance_unrounded) > 0.01
             THEN ABS(billing_variance_unrounded) ELSE 0 END
    ), 2) AS total_absolute_variance
FROM vw_billing_reconciliation_sql
GROUP BY retailer_id;
