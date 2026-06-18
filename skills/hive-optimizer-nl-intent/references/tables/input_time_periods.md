# input_time_periods

**Type:** Input | **HasRunID:** Yes

Maps PeriodID integers to actual calendar weeks (Monday dates).

## Primary Key
`RunID + PeriodID`

## Fields
| Field | Type | Description |
|---|---|---|
| `RunID` | String | PK — run identifier |
| `PeriodID` | Integer | PK — sequential week number (Period 1 = week of 2017-07-03) |
| `PeriodLabel` | String | Monday date of the week in YYYY-MM-DD format |

## Period lookup patterns

**Floor to containing week** (when user gives any date):
```sql
SELECT PeriodID FROM input_time_periods
WHERE RunID = '{run_id}' AND PeriodLabel <= 'YYYY-MM-DD'
ORDER BY PeriodLabel DESC LIMIT 1
```

**First week of a month** (default when user gives YYYY-MM):
```sql
SELECT PeriodID FROM input_time_periods
WHERE RunID = '{run_id}' AND PeriodLabel >= 'YYYY-MM-01'
ORDER BY PeriodLabel ASC LIMIT 1
```

**Last week of a month** (when user chooses "last week of month" distribution):
```sql
SELECT PeriodID FROM input_time_periods
WHERE RunID = '{run_id}' AND PeriodLabel < 'YYYY-MM+1-01'
ORDER BY PeriodLabel DESC LIMIT 1
```
(Replace `YYYY-MM+1` with the next month, e.g. for 2024-07 use `< '2024-08-01'`.)

**All weeks of a month** (when distributing a monthly value equally):
```sql
SELECT PeriodID FROM input_time_periods
WHERE RunID = '{run_id}'
  AND PeriodLabel >= 'YYYY-MM-01'
  AND PeriodLabel < 'YYYY-MM+1-01'
ORDER BY PeriodLabel ASC
```
