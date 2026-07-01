# input_aggregated_deployments

**Type:** Input | **HasRunID:** Yes

Aggregate deployment limits across customer groups and time periods.

## Primary Key
`RunID + FromPeriodID + ToPeriodID`

## Fields
| Field | Type | Required | Description |
|---|---|---|---|
| `RunID` | String | Yes | PK |
| `FromPeriodID` | Integer | Yes | PK — start of period range; FromPeriodID + 1 ≤ ToPeriodID |
| `ToPeriodID` | Integer | Yes | PK — end of period range |
| `AggDeploymentCapacity` | Float | Yes | Maximum total deployment allowed in [From, To] |

## Common mutations

Insert a new deployment cap:
```sql
INSERT INTO input_aggregated_deployments
  (RunID, FromPeriodID, ToPeriodID, AggDeploymentCapacity)
VALUES
  ('{run_id}', 461, 512, 100000000)
```

Update an existing cap:
```sql
UPDATE input_aggregated_deployments
SET AggDeploymentCapacity = 100000000
WHERE RunID = '{run_id}'
  AND FromPeriodID = 461
  AND ToPeriodID = 512
```
