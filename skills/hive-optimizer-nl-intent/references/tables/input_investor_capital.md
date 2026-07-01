# input_investor_capital

**Type:** Input | **HasRunID:** Yes

Loan financing terms for each capital raise from investors.

## Primary Key
`RunID + InvestorCapitalID`

## Fields
| Field | Type | Required | Description |
|---|---|---|---|
| `RunID` | String | Yes | PK |
| `PortfolioID` | Integer | Yes | PK |
| `InvestorCapitalID` | String | Yes | PK — unique ID for this loan/raise |
| `InvestorCapitalName` | String | Yes | Display name |
| `InvestorID` | String | Yes | FK → input_investors |
| `InterestRate` | Float | Yes | Per-period interest rate (decimal fraction, e.g. 0.015 = 1.5%) |
| `InterestType` | String | Yes | 'Simple' or 'Compound' |
| `PrincipalDeadline` | Integer | Yes | Periods by which principal must be repaid |
| `InterestRepaymentFrequency` | Integer | Yes | Periods between interest payments |
| `PrincipalRepaymentFrequency` | Integer | Yes | Periods between principal installments |
| `MinAmount` | Float | Yes | Minimum borrowing amount |
| `MaxAmount` | Float | Yes | Maximum borrowing amount |
| `NumInstallments` | Integer | Yes | Number of principal repayment installments |

## Common mutations

Change interest rate:
```sql
UPDATE input_investor_capital
SET InterestRate = 0.015
WHERE RunID = '{run_id}'
  AND InvestorCapitalID = 'Loan1'
```

Change max borrowing amount:
```sql
UPDATE input_investor_capital
SET MaxAmount = 50000000
WHERE RunID = '{run_id}'
  AND InvestorCapitalID = 'Loan1'
```

## Ambiguity note
`InterestRate` is stored as a decimal fraction (0.015 = 1.5%). If user says "1.5%", convert to 0.015 and flag in ambiguities.
