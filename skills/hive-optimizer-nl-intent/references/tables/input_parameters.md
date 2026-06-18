# input_parameters

**Type:** Input | **HasRunID:** Yes

Optimizer run configuration (key-value format). One row per parameter per RunID.

## Primary Key
`RunID + Name`

## Fields
| Field | Type | Required | Description |
|---|---|---|---|
| `RunID` | String | Yes | PK |
| `Name` | String | Yes | PK — parameter name |
| `Value` | String | Yes | Parameter value (stored as string) |

## Known parameter names
| Name | Description | Example Value |
|---|---|---|
| `Objective` | Optimization goal | `'MaximizeBankBalance'` or `'MinimizeCrossoverPoint'` |
| `StartPeriod` | PeriodID for first simulation period | `'461'` |
| `EndPeriod` | PeriodID for last simulation period | `'1812'` |
| `StartBalance` | Starting bank balance | `'1500000.00'` |
| `OverheadPerPeriod` | Fixed weekly overhead cost | `'230769.23'` |
| `MIPGap` | Solver optimality tolerance | `'0.001'` |
| `TimeoutSeconds` | Max solver runtime | `'600'` |

## Common mutations

Update a single parameter:
```sql
UPDATE input_parameters
SET Value = '0.005'
WHERE RunID = '{run_id}'
  AND Name = 'MIPGap'
```

Update start period (when PeriodID is resolved from a date):
```sql
UPDATE input_parameters
SET Value = '461'
WHERE RunID = '{run_id}'
  AND Name = 'StartPeriod'
```

## Note
These parameters are typically set via `run_params` in the intent and passed directly to `DE_NB_RunModel`. Direct SQL mutations to `input_parameters` are only needed for values not covered by `run_params`.
