# input_investor_repayment_schedule

**Type:** Input | **HasRunID:** Yes

Period-by-period schedule of interest and principal payments to investors.

## Primary Key
`RunID + InvestorCapitalID + PeriodID + PaymentType`

## Fields
| Field | Type | Required | Description |
|---|---|---|---|
| `RunID` | String | Yes | PK |
| `InvestorCapitalID` | String | Yes | PK — FK → input_investor_capital |
| `PeriodID` | Integer | Yes | PK — FK → input_time_periods |
| `PaymentType` | String | Yes | PK — 'Interest' or 'Principal' |
| `Amount` | Float | Yes | Payment amount due this period |

## Common mutations

Update a scheduled payment:
```sql
UPDATE input_investor_repayment_schedule
SET Amount = 500000
WHERE RunID = '{run_id}'
  AND InvestorCapitalID = 'Loan1'
  AND PeriodID = 85
  AND PaymentType = 'Interest'
```

## Note
This table is typically auto-generated from `input_investor_capital` loan terms. Direct mutations are rare and should be flagged in ambiguities.
