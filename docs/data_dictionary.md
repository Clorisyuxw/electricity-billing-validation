# Data Dictionary

## retailer_master.csv

| Field | Meaning |
|---|---|
| retailer_id | Anonymous simulated retailer key |
| retailer_name | Explicitly simulated display name |
| billing_frequency | Billing-cycle frequency |
| active_flag | Whether the retailer record is active |
| data_origin | Identifies the dataset as simulated |

## icp_master.csv

| Field | Meaning |
|---|---|
| icp_id | Anonymous simulated installation control point key |
| retailer_id | Retailer responsible for the connection in this simulation |
| connection_group | Residential Low User or Residential Standard User |
| control_type | Controlled or Uncontrolled |
| price_category_code | Orion public price-category code used for rate matching |
| region | Broad simulated network-area grouping |
| connection_start_date | Simulated connection start date |
| connection_end_date | Blank because all first-version ICPs remain active |
| status | Active status during the project period |
| data_origin | Identifies the record as simulated |

## monthly_consumption.csv

| Field | Meaning |
|---|---|
| consumption_id | Unique ICP and billing-month key |
| icp_id | Link to ICP master data |
| billing_month | Calendar billing month in YYYY-MM format |
| billing_period_start | First calendar day in the billing period |
| billing_period_end | Last calendar day in the billing period |
| icp_days | Inclusive number of billable connection days |
| weekend_kwh | Simulated weekend consumption quantity |
| peak_kwh | Simulated weekday peak consumption quantity |
| shoulder_kwh | Simulated weekday shoulder consumption quantity |
| off_peak_kwh | Simulated weekday off-peak consumption quantity |
| super_off_peak_kwh | Simulated super-off-peak quantity, retained at a zero rate |
| total_kwh | Sum of all mutually exclusive modelled time-band quantities |
| data_origin | Identifies the record as simulated |

