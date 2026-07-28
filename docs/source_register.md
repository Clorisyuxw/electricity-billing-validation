# Source Register

| Source | Use in project |
|---|---|
| Orion delivery price schedule applicable from 1 April 2025 | Official 2025 component prices and units |
| Orion delivery price schedule applicable from 1 April 2026 | Official 2026 component prices and units |
| Orion pricing update summary for prices applying from 1 April 2026 | Effective-date and pricing-change context |
| [Electricity Authority — New Zealand's electricity sector](https://www.ea.govt.nz/your-power/new-zealands-electricity-sector/) | Market participant and electricity supply-chain context |
| [Electricity Authority — Electricity Registry](https://www.ea.govt.nz/industry/retail/electricity-registry/) | ICP, Registry and participant information-sharing context |
| [Electricity Industry Participation Code 2010 — Part 11](https://www.ea.govt.nz/code-and-compliance/the-code-electricity-industry-participation-code-2010/part-11-registry-information-management/1118a-registry-manager-to-advise-metering-equipment-providers/) | Registry information-management context |
| [Electricity Industry Participation Code 2010 — Part 15](https://www.ea.govt.nz/code-and-compliance/the-code-electricity-industry-participation-code-2010/part-15-reconciliation/1512-accuracy-of-submitted-information/) | Market reconciliation context and boundary clarification |

## Source interpretation

- The schedules describe wholesale electricity delivery prices charged by Orion to electricity retailers and directly contracted customers.
- Delivery Price is the sum of Distribution Price, Pass-through & Recoverable Price, and Transmission Price.
- All listed prices exclude GST.
- The 2026 schedule applies from 1 April 2026.

The Electricity Authority and Code sources provide business and regulatory context only. They are not implemented as source rules in the billing calculation, and the project does not claim Registry integration or Part 15 market-reconciliation compliance. See [New Zealand Electricity Market Context](nz_electricity_market_context.md).

## Published rounding note

Three selected 2025 rows have a difference of no more than $0.00010 between the sum of the three displayed price components and the published Delivery Price. This is consistent with independently rounded published components. The project preserves Orion's published Delivery Price as the billing rate and treats differences up to $0.00010 as source rounding, rather than altering official values.
