-- Reconcile SQL-calculated expected charges to simulated system billing.

DROP VIEW IF EXISTS vw_billing_reconciliation_sql;

CREATE VIEW vw_billing_reconciliation_sql AS
SELECT
    e.consumption_id,
    e.icp_id,
    e.retailer_id,
    e.price_category_code,
    e.region,
    e.billing_month,
    e.price_year,
    e.expected_delivery_charge_unrounded,
    e.expected_delivery_charge,
    s.system_billed_amount_unrounded,
    s.system_billed_amount,
    s.system_line_count,
    s.system_billed_amount_unrounded
        - e.expected_delivery_charge_unrounded AS billing_variance_unrounded,
    ROUND(
        s.system_billed_amount_unrounded
            - e.expected_delivery_charge_unrounded,
        2
    ) AS billing_variance,
    CASE
        WHEN ABS(
            s.system_billed_amount_unrounded
                - e.expected_delivery_charge_unrounded
        ) <= 0.01 THEN 'PASS'
        ELSE 'REVIEW'
    END AS validation_status,
    CASE
        WHEN s.system_billed_amount_unrounded
                - e.expected_delivery_charge_unrounded > 0.01
            THEN 'Overbilled'
        WHEN s.system_billed_amount_unrounded
                - e.expected_delivery_charge_unrounded < -0.01
            THEN 'Underbilled'
        ELSE 'No material variance'
    END AS variance_direction
FROM vw_expected_billing_summary_sql AS e
INNER JOIN system_billing AS s
    ON e.consumption_id = s.consumption_id;
