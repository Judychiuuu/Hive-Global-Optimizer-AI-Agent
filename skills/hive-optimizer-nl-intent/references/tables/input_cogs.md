# input_cogs

**Type:** Input | **HasRunID:** Yes

Cost of Goods Sold (lending costs) per funded dollar, by customer group, COGS type, period, and loan age.

## Primary Key
`RunID + CustomerGroupID + CogsTypeID + PeriodID + PeriodsSinceDeployment`

## Fields
| Field | Type | Required | Description |
|---|---|---|---|
| `RunID` | String | Yes | PK |
| `CustomerGroupID` | String | Yes | PK — FK → input_customer_groups |
| `CogsTypeID` | String | Yes | PK — FK → input_cogs_types |
| `PeriodID` | Integer | Yes | PK — FK → input_time_periods |
| `PeriodsSinceDeployment` | Integer | Yes | PK — loan age in periods (0 = deployment period) |
| `CogsLabel` | String | Yes | 'Longitudinal' or 'CrossSectional' |
| `CogsRate` | Float | Yes | Cost per funded $1 (new borrowers) |
| `RepeatCogsRate` | Float | Yes | Cost per funded $1 (repeat borrowers) |

## COGS Types
- **Longitudinal** (variable, scale with deployments): Payment Processing, Call Center, Other
- **CrossSectional** (fixed period costs): Underwriting, Marketing

## Common mutations

Update a single COGS rate for a customer group in a specific period:
```sql
UPDATE input_cogs
SET CogsRate = 0.25
WHERE RunID = '{run_id}'
  AND CustomerGroupID = 'C1'
  AND CogsTypeID = 'Underwriting'
  AND PeriodID = 85
  AND PeriodsSinceDeployment = 0
```

Update across a range of periods:
```sql
UPDATE input_cogs
SET CogsRate = 0.25
WHERE RunID = '{run_id}'
  AND CustomerGroupID = 'C1'
  AND CogsTypeID = 'Underwriting'
  AND PeriodID BETWEEN 85 AND 120
```

## Ambiguity note
When user says "COGS rate" without specifying a CogsTypeID, ask: "Which COGS type? (Underwriting, Marketing, Payment Processing, Call Center, Other)"
