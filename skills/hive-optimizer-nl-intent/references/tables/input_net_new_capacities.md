# input_net_new_capacities

**Type:** Input | **HasRunID:** Yes

Defines initial per-period availability of net new investor capital. Used when `EnableNetNewConstraint` = `Yes` in the `input_parameters` table.

## Primary Key
`RunID + InvestorCapitalID + PeriodID`

## Fields
| Field | Type | Required | Description |
|---|---|---|---|
| `RunID` | String | Yes | PK |
| `InvestorCapitalID` | String | Yes | PK — identifier for a loan from an investor (FK → input_investor_capital) |
| `PeriodID` | Integer | Yes | PK — identifier for the period of the new capital raise |
| `NetNewCapacity` | Float | Yes | Amount of new capital available in that period |
| `RollRate` | Float | Yes | Fraction (0–1) of rolling-off principal (CapitalRollingOff) that is available as 'Roll' Capital Raise |

## Common mutations

Set net new capacity for a specific investor and period:
```sql
UPDATE input_net_new_capacities
SET NetNewCapacity = 1000000
WHERE RunID = '{run_id}'
  AND InvestorCapitalID = 'IC1'
  AND PeriodID = 448
```

Update roll rate:
```sql
UPDATE input_net_new_capacities
SET RollRate = 0.5
WHERE RunID = '{run_id}'
  AND InvestorCapitalID = 'IC1'
```

## Ambiguity note
`RollRate` is a decimal fraction (0–1). If a user says "50% roll rate", convert to 0.5.
