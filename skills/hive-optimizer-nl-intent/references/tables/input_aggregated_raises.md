# input_aggregated_raises

**Type:** Input | **HasRunID:** Yes

Aggregate capital raise targets or limits across a range of periods.

## Primary Key
`RunID + FromPeriodID + ToPeriodID + ConstraintType`

## Fields

> **No `InvestorCapitalID` field.** This table constrains *total* capital raised across ALL investors for a period range. Do NOT ask which investor — that field does not exist here. If the user wants an investor-specific fixed amount, use `input_fix_raises` instead.

| Field | Type | Required | Description |
|---|---|---|---|
| `RunID` | String | Yes | PK |
| `FromPeriodID` | Integer | Yes | PK — start of period range (FK → input_time_periods) |
| `ToPeriodID` | Integer | Yes | PK — end of period range; FromPeriodID ≤ ToPeriodID |
| `AggRaises` | Float | Yes | Max or exact capital that can be raised in [From, To] |
| `ConstraintType` | String | Yes | PK — 'LessThanOrEqualTo' or 'EqualTo' |

## Common mutations

Insert a new raise constraint:
```sql
INSERT INTO input_aggregated_raises
  (RunID, FromPeriodID, ToPeriodID, AggRaises, ConstraintType)
VALUES
  ('{run_id}', 465, 521, 80000000, 'LessThanOrEqualTo')
```

Update an existing constraint:
```sql
UPDATE input_aggregated_raises
SET AggRaises = 80000000
WHERE RunID = '{run_id}'
  AND FromPeriodID = 465
  AND ToPeriodID = 521
  AND ConstraintType = 'LessThanOrEqualTo'
```

## Ambiguity note
When user says "capital raised is X", ask whether it's a ceiling ('LessThanOrEqualTo') or exact target ('EqualTo'), and confirm whether it's the total for the period or a per-period amount.
