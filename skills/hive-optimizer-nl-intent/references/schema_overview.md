# Schema Overview — Hive Global Optimizer

## RunID Architecture

Every optimization run has a unique `RunID` (UUID string). Tables are **partitioned by RunID** — each run copies base data from a prior run (`DE_NB_CopyRun`), assigns the new RunID, then applies scenario-specific SQL before solving.

**Run-scoped tables** (always filter `WHERE RunID = '{run_id}'`):
All 14 run-specific input tables plus all 11 output tables. Every `sql_mutation` targeting these must include the RunID WHERE clause.

**Reference tables without RunID** (shared across all runs, no RunID filter):
`input_portfolios`, `input_customer_groups`, `input_cogs_types`, `input_investors`,
`input_direct_mail_curves`, `input_fix_deployments`, `input_fix_direct_mails`,
`input_fix_raises`, `input_portfolio_deployments`

**RunID generation**: always created by `DE_NB_Get_New_Run_Id` → then used by `DE_NB_CopyRun`. Never manually assigned.

---

## Period System (Weekly)

- Periods are **weekly**, Monday start
- `PeriodLabel` format: `YYYY-MM-DD` (the Monday of that week)
- Period 1 = `2017-07-03`
- All temporal foreign keys use `PeriodID` (integer)

**Period lookup — floor to containing week:**
```sql
SELECT PeriodID FROM input_time_periods
WHERE RunID = '{run_id}' AND PeriodLabel <= 'YYYY-MM-DD'
ORDER BY PeriodLabel DESC LIMIT 1
```

**First week of a month:**
```sql
SELECT PeriodID FROM input_time_periods
WHERE RunID = '{run_id}' AND PeriodLabel >= 'YYYY-MM-01'
ORDER BY PeriodLabel ASC LIMIT 1
```

---

## Tool Execution Order

The main orchestrator (`DE_NB_Main`) calls tools in this sequence:

1. **`DE_NB_Get_New_Run_Id`** → returns `new_run_id` (UUID)
2. **`DE_NB_CopyRun`** (`old_run_id`, `new_run_id`) → copies all run-scoped tables
3. **`DE_NB_Apply_Scenario`** (`run_id`, `sql_statements`) → executes `sql_mutations`, substituting `{run_id}` with the actual `new_run_id`
4. **`DE_NB_RunModel`** (`run_id`, `run_params`) → runs the MIP optimizer

---

## Input Tables (23 total)

| Table | Primary Key | HasRunID | Common Use |
|---|---|---|---|
| `input_aggregated_deployments` | RunID + FromPeriodID + ToPeriodID | Yes | Portfolio deployment constraints |
| `input_aggregated_raises` | RunID + FromPeriodID + ToPeriodID + ConstraintType | Yes | Capital raise constraints |
| `input_cogs` | RunID + CustomerGroupID + CogsTypeID + PeriodID + PeriodsSinceDeployment | Yes | Cost rates per customer group |
| `input_cogs_types` | CogsTypeID | No | COGS taxonomy (Longitudinal / CrossSectional) |
| `input_customer_capacities` | RunID + CustomerGroupID + PeriodID | Yes | Deployment capacity per segment |
| `input_customer_groups` | CustomerGroupID | No | Segment definitions |
| `input_direct_mail_curves` | CustomerGroupID + PeriodID + PeriodsSinceCogs | No | DM campaign response curves |
| `input_fix_deployments` | CustomerGroupID + OriginalPeriodID + PeriodID + IsRepeat | No | Pre-committed deployments |
| `input_fix_direct_mails` | CustomerGroupID + PeriodID | No | Scheduled DM COGS payments |
| `input_fix_raises` | InvestorCapitalID + PeriodID | No | Pre-committed capital raises |
| `input_investor_capital` | RunID + InvestorCapitalID | Yes | Loan terms per investor |
| `input_investors` | InvestorID | No | Investor master list |
| `input_investor_repayment_schedule` | RunID + InvestorCapitalID + PeriodID + PaymentType | Yes | Period-by-period payment schedule |
| `input_net_new_capacities` | RunID + InvestorCapitalID + PeriodID | Yes | Marketing-driven capacity uplift |
| `input_parameters` | RunID + Name | Yes | Optimizer run config (key-value) |
| `input_performance_curves` | RunID + CustomerGroupID + PeriodID + PeriodsSinceDeployment | Yes | Return/interest/charge-off curves |
| `input_periods_config` | RunID + PeriodID | Yes | Per-period balance floor, deploy cap, COGS factor |
| `input_portfolios` | PortfolioID | No | Portfolio definitions |
| `input_portfolio_deployments` | PortfolioID + FromPeriodID + ToPeriodID + ConstraintType | No | Portfolio-level deploy targets |
| `input_portfolios_config` | RunID + PortfolioID + PeriodID | Yes | Portfolio-to-customer mapping |
| `input_relative_deployments` | RunID + Year + Month | Yes | Deployment mix ratios |
| `input_repeats_distribution` | RunID + CustomerGroupID + PeriodID + PeriodsSinceDeployment | Yes | Repeat vs. new customer split |
| `input_time_periods` | RunID + PeriodID | Yes | PeriodID ↔ PeriodLabel (YYYY-MM-DD) calendar |

## Output Tables (11 total)

All output tables are run-scoped (HasRunID = Yes). See `schema_reference.md` for full field lists.

| Table | Description |
|---|---|
| `output_aggregated_deployments_slacks` | Unused capacity vs. aggregated deploy constraints |
| `output_customer_deployments_slacks` | Unused capacity per customer group and period |
| `output_deployments_slacks` | Unused global deploy capacity per period |
| `output_portfolio_deployments_slacks` | Unused capacity vs. portfolio constraints |
| `output_kpis` | Key metrics: crossover point, ending balance, ROIC, etc. |
| `output_ledger` | Full cash flow waterfall per period |
| `output_ledger_pivot` | Pivoted ledger for time-series comparison |
| `output_balances` | Bank balance per period |
| `output_financial` | Annual financial summary |
| `output_raises_slacks` | Unused capacity vs. raise constraints |
| `output_balances_slacks` | Balance floor slack per period |
