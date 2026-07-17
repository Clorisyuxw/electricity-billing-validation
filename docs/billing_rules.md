# Billing Rules

## Business boundary

The model calculates Orion electricity delivery charges using public wholesale delivery prices. It does not calculate a retailer's complete consumer electricity bill. Prices exclude GST.

## Price selection

- Billing periods ending on or before 31 March 2026 use the schedule effective from 1 April 2025.
- Billing periods starting on or after 1 April 2026 use the schedule effective from 1 April 2026.
- First-version periods are complete calendar months and do not cross the price-change date.
- A future version would need to split and prorate a period that crosses an effective-date boundary.

## Category selection

Each ICP uses the price category recorded in `icp_master.csv`. The category and component name jointly select one official component code and delivery price for the applicable year.

## Fixed charge

`Fixed charge = ICP days x fixed daily delivery price`

The fixed component uses a price unit of dollars per connection per day.

## Variable charge

For each time band:

`Variable charge = time-band kWh x applicable delivery price per kWh`

Weekend, Peak, Shoulder, Off Peak and Super Off Peak quantities are mutually exclusive in the simulated dataset.

## Super Off Peak

The selected public schedules show a zero Super Off Peak delivery price. Consumption is retained for a complete total, matched to the official zero-rate component, and produces a zero charge.

## Rounding

- Source delivery prices retain the precision published by Orion.
- Component calculations retain unrounded values for reconciliation.
- The monthly expected delivery charge is rounded to two decimal places only after all components are summed.
- Later system-billing reconciliation will use a one-cent tolerance.

## Known scope limitation

Because all first-version billing periods are complete months, price selection can use the billing-period start date after confirming the price remains effective through the period end. This logic must not be reused unchanged for a bill that crosses 1 April.
