# input_performance_curves

**Type:** Input | **HasRunID:** Yes

Expected financial performance of deployed capital over time (return rates, interest, charge-offs).

## Primary Key
`RunID + CustomerGroupID + PeriodID + PeriodsSinceDeployment`

## Fields
| Field | Type | Required | Description |
|---|---|---|---|
| `RunID` | String | Yes | PK |
| `PortfolioID` | Integer | Yes | PK |
| `CustomerGroupID` | String | Yes | PK — FK → input_customer_groups |
| `PeriodID` | Integer | Yes | PK — deployment period |
| `PeriodsSinceDeployment` | Integer | Yes | PK — loan age (0 = deployment period) |
| `ReturnRate` | Float | Yes | Repayment rate for new borrowers as % of deployment |
| `RepeatReturnRate` | Float | Yes | Repayment rate for repeat borrowers (usually higher) |
| `InterestPercentage` | Float | Yes | Interest income % of deployment (new borrowers) |
| `InterestPercentageRepeats` | Float | Yes | Interest income % (repeat borrowers) |
| `ChargeOffPercentage` | Float | Yes | Expected credit losses % of deployment (new) |
| `ChargeOffPercentageRepeats` | Float | Yes | Expected credit losses % (repeat) |

## Common mutations

Scale ReturnRate and RepeatReturnRate by a factor across a period range:
```sql
UPDATE input_performance_curves
SET ReturnRate = ReturnRate * 0.80,
    RepeatReturnRate = RepeatReturnRate * 0.80
WHERE RunID = '{run_id}'
  AND PeriodID BETWEEN 465 AND 521
```

## Ambiguity note
"Scale performance curves by 20%" means multiply by `(1 - 0.20) = 0.80`. Confirm whether the user means an increase (+20%) or decrease (-20%) and flag in ambiguities.
