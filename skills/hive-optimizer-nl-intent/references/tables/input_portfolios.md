# input_portfolios

**Type:** Input | **HasRunID:** Yes

Defines the portfolios available in the optimization, including whether Hive directly manages servicing and origination.

## Primary Key
`RunID + PortfolioID`

## Fields
| Field | Type | Required | Description |
|---|---|---|---|
| `RunID` | String | Yes | PK |
| `PortfolioID` | Integer | Yes | PK — unique identifier for the portfolio |
| `PortfolioLabel` | String | Yes | Human-readable label for the portfolio (e.g. `'Explore Credit'`, `'Clover'`, `'Nora'`) |
| `Managed` | String | Yes | `'Yes'` if Hive does servicing and origination (COGS are usually higher); `'No'` if Hive doesn't directly originate or service (COGS are lower, UM is usually fixed) |

## Common mutations

Change a portfolio's managed status:
```sql
UPDATE input_portfolios
SET Managed = 'No'
WHERE RunID = '{run_id}'
  AND PortfolioID = 2
```

## Ambiguity note
When a user references a portfolio by label (e.g. "Explore portfolio"), look up the corresponding `PortfolioID` from this table. `Managed` affects COGS assumptions — flag if the user changes this field, as it has downstream cost implications.
