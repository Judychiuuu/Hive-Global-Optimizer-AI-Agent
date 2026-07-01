# input_fix_deployments

**Type:** Input | **HasRunID:** Yes

Fix the exact amount to be lent to a specific portfolio and customer group in a specific period.

## Primary Key
`RunID + PortfolioID + CustomerGroupID + PeriodID`

## Fields

> **Always use `PeriodID`, never `OriginalPeriodID`.** `OriginalPeriodID` records the period in which the loan was originally originated; it is informational only. All period-based queries and mutations must target `PeriodID`.

| Field | Type | Required | Description |
|---|---|---|---|
| `RunID` | String | Yes | PK |
| `PortfolioID` | Integer | Yes | PK — which portfolio the deployment belongs to |
| `CustomerGroupID` | String | Yes | PK — which customer group receives the deployment |
| `PeriodID` | Integer | Yes | PK — the period in which the deployment occurs (FK → input_time_periods) |
| `OriginalPeriodID` | Integer | Yes | The period the loan was originally originated; informational only — do NOT use as a period reference |
| `IsRepeat` | String | Yes | 'Yes' if this is a repeat/rollover of a prior deployment, 'No' otherwise |
| `Quantity` | Float | Yes | Exact amount to deploy to this portfolio + customer group in this period |

## Common mutations

Fix a deployment amount for a specific portfolio, customer group, and period:
```sql
INSERT INTO input_fix_deployments
  (RunID, PortfolioID, CustomerGroupID, OriginalPeriodID, PeriodID, IsRepeat, Quantity)
VALUES
  ('{run_id}', 1, 'C1', 190, 215, 'Yes', 4300)
```

Update an existing fixed deployment:
```sql
UPDATE input_fix_deployments
SET Quantity = 4300
WHERE RunID = '{run_id}'
  AND PortfolioID = 1
  AND CustomerGroupID = 'C1'
  AND PeriodID = 215
```

Remove a fixed deployment constraint:
```sql
DELETE FROM input_fix_deployments
WHERE RunID = '{run_id}'
  AND PortfolioID = 1
  AND CustomerGroupID = 'C1'
  AND PeriodID = 215
```

## Ambiguity note
If the user refers to a period without clarifying, always resolve to `PeriodID`. If the user asks about "when a loan was originally made", that is `OriginalPeriodID` — but still filter or mutate using `PeriodID`. If the user does not specify `IsRepeat`, default to 'Yes' for rollover/repeat contexts and 'No' for new deployments.
