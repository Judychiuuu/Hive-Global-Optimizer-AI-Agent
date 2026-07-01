# input_portfolio_deployments

**Type:** Input | **HasRunID:** Yes

Defines the amount of capital that must or can be deployed into a portfolio within a specific period range. Acts as a deployment constraint per portfolio over time.

## Primary Key
`RunID + PortfolioID + FromPeriodID + ToPeriodID`

## Fields
| Field | Type | Required | Description |
|---|---|---|---|
| `RunID` | String | Yes | PK |
| `PortfolioID` | Integer | Yes | PK — FK → input_portfolios |
| `FromPeriodID` | Integer | Yes | PK — start of the period range for this deployment constraint |
| `ToPeriodID` | Integer | Yes | PK — end of the period range for this deployment constraint |
| `ConstraintType` | String | Yes | How the constraint is applied — `'Equal'` (exact amount must be deployed) or `'LessThanOrEqual'` (up to that amount) |
| `QuantityDeployed` | Float | Yes | Amount of capital to deploy in the given period range |

## Common mutations

Set a deployment target for a portfolio in a period range:
```sql
UPDATE input_portfolio_deployments
SET QuantityDeployed = 500000
WHERE RunID = '{run_id}'
  AND PortfolioID = 2
  AND FromPeriodID = 94
  AND ToPeriodID = 94
```

Change constraint type to an upper bound instead of exact:
```sql
UPDATE input_portfolio_deployments
SET ConstraintType = 'LessThanOrEqual'
WHERE RunID = '{run_id}'
  AND PortfolioID = 2
```

## Ambiguity note
When a user says "deploy X in period Y", check whether `FromPeriodID = ToPeriodID = Y` (single-period constraint) or a range is intended. Also clarify whether the constraint is `Equal` or `LessThanOrEqual` if not stated.
