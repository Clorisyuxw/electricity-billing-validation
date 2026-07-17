# Simulation Assumptions

## Purpose

The simulated datasets provide anonymous, reproducible records for testing price selection, billing calculations and discrepancy detection. They are not Orion operational data.

## Population

- 500 active simulated ICPs
- Five anonymous simulated retailers
- Four monthly billing periods from February to May 2026
- Price-category mix is weighted toward controlled residential connections, based broadly on the relative connection counts displayed in Orion's 2026 public price schedule

## Consumption

- Monthly consumption is generated from a positive lognormal distribution so records vary without producing negative values.
- Residential Standard User connections have a higher modelled average than Residential Low User connections.
- Monthly factors rise from February to May to represent increasing cooler-season demand. These are modelling assumptions, not estimates of Orion's actual demand.
- Each monthly total is allocated across mutually exclusive Weekend, Peak, Shoulder, Off Peak and Super Off Peak quantities.
- Super Off Peak consumption is retained for a complete modelled total but has a published delivery price of zero in the selected schedules and therefore produces no charge.

## Dates

- All simulated ICPs are active for the entire four-month project period.
- Billing periods cover complete calendar months.
- February and March 2026 use the schedule effective from 1 April 2025.
- April and May 2026 use the schedule effective from 1 April 2026.

## Reproducibility

The random seed is fixed at 20260716. Re-running the generation script produces the same data.

