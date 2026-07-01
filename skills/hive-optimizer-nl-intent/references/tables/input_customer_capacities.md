# input_customer_capacities

**Type:** Input | **HasRunID:** Yes

Maximum deployment capacity per customer group per period (demand saturation constraints).

## Primary Key
`RunID + CustomerGroupID + PeriodID`

## Fields
| Field | Type | Required | Description |
|---|---|---|---|
| `RunID` | String | Yes | PK |
| `PortfolioID` | Integer | Yes | PK |
| `CustomerGroupID` | String | Yes | PK — FK → input_customer_groups |
| `PeriodID` | Integer | Yes | PK — FK → input_time_periods |
| `DeploymentCapacity` | Float | Yes | Maximum capital deployable to this segment this period |

## Common mutations

Set capacity for a single period:
```sql
UPDATE input_customer_capacities
SET DeploymentCapacity = 5000000
WHERE RunID = '{run_id}'
  AND CustomerGroupID = 'C1'
  AND PortfoliosID = 1
  AND PeriodID = 85
```

Set capacity across a range of periods:
```sql
UPDATE input_customer_capacities
SET DeploymentCapacity = 5000000
WHERE RunID = '{run_id}'
  AND CustomerGroupID = 'C1'
  AND PortfoliosID = 1
  AND PeriodID BETWEEN 85 AND 120
```
