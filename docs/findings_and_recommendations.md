# Findings and Recommendations

## Scope reminder

All findings below relate to a controlled portfolio simulation. Official Orion 2025 and 2026 delivery price schedules were used, while ICP, retailer, consumption and system-billing records were simulated.

## Validated billing population

- 500 simulated ICPs
- Five anonymous simulated retailers
- Four complete monthly billing periods from February to May 2026
- 2,000 monthly bills
- 12,000 expected component calculations
- Total expected delivery charges: $138,544.09

## Controlled billing exceptions

Fifty bills contained one controlled exception each. The independent rules detected and correctly classified all 50, with no false-positive or false-negative issue classifications.

| Issue type | Bills | Net variance | Absolute impact |
|---|---:|---:|---:|
| Calculation error | 10 | $52.50 | $52.50 |
| Duplicate consumption | 10 | $244.86 | $244.86 |
| Incorrect ICP days | 10 | $16.31 | $16.31 |
| Old price applied | 10 | -$88.95 | $88.95 |
| Wrong price category | 10 | $22.88 | $24.60 |
| Total | 50 | $247.60 | $427.22 |

Net variance understates total control exposure because overbilling and underbilling partly offset. Total absolute variance is therefore the stronger workload and risk-monitoring measure.

## Price-change impact

Holding April and May quantities, categories and connection days constant, applying 2026 rates instead of 2025 rates increased simulated expected delivery charges by $9,528.74:

- April: $4,648.92
- May: $4,879.82

This is a rate-only scenario, not Orion's actual revenue movement. Actual period-to-period revenue can also change because of consumption, connection counts, category mix and data corrections.

## Recommended controls

1. **Effective-date control** - confirm every component rate covers the complete billing period, particularly around 1 April.
2. **ICP category validation** - compare the billing category with controlled master data before price matching.
3. **Duplicate-component control** - enforce or test uniqueness for billing period, ICP and component.
4. **Fixed-day validation** - reconcile fixed-charge quantity to inclusive active connection days.
5. **Independent amount recalculation** - verify quantity multiplied by delivery price equals the stored system line amount.
6. **Expected-versus-system reconciliation** - flag differences above the agreed materiality threshold before release or for investigation.
7. **Retailer exception summary** - group affected bills and financial impact by retailer to support clear issue resolution.
8. **Price-change regression testing** - retain boundary-date, category and component test cases for annual pricing updates.

## Limitations

- The workflow does not represent Orion's internal billing system or approval process.
- It covers four residential price categories and excludes business, irrigation and major-customer pricing.
- It excludes GST, retail energy charges, loss factors, export credits and Winter Peak Injection.
- Billing periods are complete calendar months and do not cross the annual price-change date.
- Consumption patterns are reproducible modelling assumptions, not forecasts or estimates of Orion demand.
