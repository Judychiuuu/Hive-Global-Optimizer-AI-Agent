# input_fix_raises

**Type:** Input | **HasRunID:** Yes

Fix the exact amount to be raised from a specific investor in a specific period.

## Primary Key
`RunID + InvestorCapitalID + PeriodID`

## Fields

> **Investor-specific.** Unlike `input_aggregated_raises`, each row pins a single `InvestorCapitalID` to an exact quantity in one period. Use this table when the user specifies *who* they are raising from AND an exact amount in a given period.

| Field | Type | Required | Description |
|---|---|---|---|
| `RunID` | String | Yes | PK |
| `InvestorCapitalID` | String | Yes | PK — which investor/capital source (FK → input_investor_capital) |
| `PeriodID` | Integer | Yes | PK — the period in which the raise occurs (FK → input_time_periods) |
| `Quantity` | Float | Yes | Exact amount to raise from this investor in this period |

## Common mutations

Fix a raise amount for a specific investor and period:
```sql
INSERT INTO input_fix_raises
  (RunID, InvestorCapitalID, PeriodID, Quantity)
VALUES
  ('{run_id}', 'IC1', 465, 636795.0346657335)
```

Update an existing fixed raise:
```sql
UPDATE input_fix_raises
SET Quantity = 636795.0346657335
WHERE RunID = '{run_id}'
  AND InvestorCapitalID = 'IC1'
  AND PeriodID = 465
```

Remove a fixed raise constraint:
```sql
DELETE FROM input_fix_raises
WHERE RunID = '{run_id}'
  AND InvestorCapitalID = 'IC1'
  AND PeriodID = 465
```

## Ambiguity note
If the user specifies a raise amount without naming an investor, check whether they mean a total constraint (use `input_aggregated_raises`) or an investor-specific pin (use this table). If they name an investor but give a range of periods instead of one period, insert one row per period.
