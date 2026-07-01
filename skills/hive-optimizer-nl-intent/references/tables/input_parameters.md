# input_parameters

**Type:** Input | **HasRunID:** Yes

Optimizer run configuration. **Wide table — one row per RunID, each parameter is its own column** (not a key-value table). Values are stored as strings.

## Primary Key
`RunID`

## Fields
`RunID` (String, PK) + one String column per parameter. See parameter tables below for all column names.

---

## How parameters are set

Parameters fall into two categories:

| Category | How it's set | LLM should generate SQL? |
|---|---|---|
| **Form-driven** | Collected in the app's Step 3.3 Run Parameters form. Written to this table via `UPDATE input_parameters` statements generated at form confirmation (injected into `sql_mutations` before Step 4.1). | **No** — values come directly from the form. |
| **SQL-only** | Not exposed in the form. Must be set via explicit SQL mutation if a non-default value is needed. | **Yes** — generate `UPDATE input_parameters SET Value = '...' WHERE RunID = '{run_id}' AND Name = '...'` |

---

## Form-driven parameters

Set by the Step 3.3 form. SQL mutations for these are generated automatically from the form values — **do not generate SQL for these from a user's NL command**.

| Name | Form field | Default | Description |
|---|---|---|---|
| `StartPeriod` | Start Period | `461` | PeriodID for the first period of the simulation — the first time period for which decisions are made |
| `EndPeriod` | Start Period + Duration | `1812` | PeriodID for the last period of the simulation. Derived as `StartPeriod + Duration` (default duration: 1351 periods) |
| `MainObjectiveFunction` | Objective Function | `'Maximize Bank Balance'` | Primary optimization goal. See [Objective options](#mainobjectivefunction-options) below |
| `MIPGap` | MIP Gap | `0.001` | Mixed Integer Programming Gap — acceptable difference between the best-known feasible solution and the theoretical optimal. Controls solver stopping criteria to balance solution quality against computational cost |

---

## SQL-only parameters

Not exposed in the form. Generate SQL mutations for these when the user's intent requires a non-default value.

| Name | Default | Description |
|---|---|---|
| `StartBalance` | — | Initial bank balance at the beginning of `StartPeriod` (equivalently, the bank balance at the end of the period immediately before `StartPeriod`) |
| `MinCrossoverPoint` | — | Target PeriodID for crossover. Only used when `MainObjectiveFunction = 'Maximize Bank Balance'` to constrain the solution to a desired crossover point (feasible scenarios only) |
| `IsInfeasible` | `'No'` | If `'Yes'`, skips the base objective for scenarios already known to be infeasible and runs the infeasibility slack approach directly |
| `InfeasibilitySlackApproach` | — | Strategy for relaxing constraints when infeasible. See [Slack approach options](#infeasibilityslackapproach-options) below |
| `InfeasibilitySlackObjective` | — | Objective function used when running the infeasibility slack model |
| `SkipSlackModel` | — | If `'Yes'`, skips running the infeasibility slack model even when the primary model is infeasible |
| `ProhibitMoneySamePeriod` | — | If `'Yes'`, capital raised or topline cashflow cannot be deployed in the same period it is received |
| `EnableNetNewConstraint` | — | Controls how net new investor capital can be introduced. See [Net new constraint](#enablenetnewconstraint) below |
| `NetNewWindow` | — | Frequency (in periods) at which `NetNewCapacity` may increase by the allowed maximum percentage |
| `NetNewMaxPercentage` | — | Maximum allowable increase in new capital per `NetNewWindow` |
| `EnableRelativeDeployments` | `'No'` | Controls seasonal deployment shaping. See [Relative deployments](#enablerelativedeployments) below |
| `RelativeDeploymentsRelTol` | — | Fraction of the main objective (0–1) you are willing to sacrifice to follow the seasonal deployment pattern |
| `RelativeDeploymentsAbsTol` | — | Absolute dollar amount allowed to be lost in objective value to follow the seasonal deployment pattern |
| `DeviationMinimizationMode` | — | How deviations from the seasonal curve are penalized. Only applies when `EnableRelativeDeployments = 'Yes'`. See [Deviation mode](#deviationminimizationmode) below |
| `RelativeDeploymentsMaxDeviation` | — | Maximum allowable deviation from the seasonal deployment curve in any single period. Only applies when `EnableRelativeDeployments = 'Yes'` |
| `OptimalObjectiveValue` | — | Best objective value (e.g. final balance) achievable without seasonal shaping. Computed by first running the model with `EnableRelativeDeployments = 'No'`, stored here as a baseline for the seasonal-shaping run |
| `SolverParams` | — | JSON string of Gurobi solver parameters. See [Solver params](#solverparams) below |

---

## MainObjectiveFunction options

| Value | Behaviour |
|---|---|
| `'Maximize Bank Balance'` | Maximizes the final bank balance while also solving for the crossover point. Optionally, set `MinCrossoverPoint` to a PeriodID to constrain the solution to a desired crossover point (feasible scenarios only) |
| `'Minimize Crossover Point'` | Minimizes the crossover point — finds the earliest period at which the cumulative cash position turns positive from the start of the simulation |

---

## InfeasibilitySlackApproach options

Introduces slack variables to relax constraints so the model remains solvable when strictly infeasible.

| Value | Constraint relaxed | Constraint source | Slack output |
|---|---|---|---|
| `'Balances'` | Minimum bank balance | `input_periods_config.BalanceLowerBound` | `output_balances_slacks.BalanceLowerBoundSlack` |
| `'Deployments'` | Minimum deployment capacity increase (per customer, per portfolio, global) | `input_customer_capacities.DeploymentCapacity`<br>`input_portfolio_deployments.QuantityDeployed`<br>`input_periods_config.DeploymentCapacity` | `output_customer_deployments_slacks.DeploymentCapacitySlack`<br>`output_deployments_slacks.DeploymentCapacitySlack`<br>`output_portfolio_deployments_slacks.QuantityDeployedSlack` |
| `'Raises'` | Raise constraints | `input_investor_capital.MaxAmount`<br>`input_aggregated_raises.AggRaises`<br>`input_fix_raises.Quantity`<br>`input_net_new_capacities.NetNewCapacity` | `output_raises_slacks.RaiseSlack` |
| `'DeploymentsAndRaises'` | Both deployment and raise constraints | (combined from above) | (combined from above) |

---

## EnableNetNewConstraint

| Value | Behaviour |
|---|---|
| `'Yes'` | Restricts new investor capital using `NetNewWindow` and `NetNewMaxPercentage`. At least `NetNewWindow` rows with non-zero capacity must be defined in `net_new_capacities` |
| `'No'` | No limit on how much new investor capital can be added via `net_new_capacities`. Investor capital constraints from `input_investor_capital` are still enforced |

---

## EnableRelativeDeployments

| Value | Behaviour |
|---|---|
| `'No'` | Feature disabled. Model follows standard constraints and objective. `relative_deployments` table is ignored |
| `'Yes'` | Model attempts to follow a seasonal deployment pattern from the `relative_deployments` table while still honoring all constraints. Requires rows for every month/year from `StartPeriod` to `EndPeriod`, each with a `RelativeWeight` that sums to 1 annually |

---

## DeviationMinimizationMode

Only applies when `EnableRelativeDeployments = 'Yes'`.

| Value | Behaviour |
|---|---|
| `'Sum'` | Minimizes the **total** deviation across all periods from the seasonal curve. Allows short-term spikes but keeps aggregate deviation small |
| `'Max'` | Minimizes the **maximum** single-period deviation. Produces a smoother, more uniform curve, possibly at the cost of higher total deviation |

---

## SolverParams

JSON string of Gurobi parameters. V1.15.1 ships with the following defaults per objective:

**Minimize Crossover Point:**
```json
{
  "Primary": {
    "Method": 0,
    "PreDual": 1,
    "NodeMethod": 0,
    "Cuts": 0,
    "Aggregate": 0,
    "PreSparsify": 2,
    "PrePasses": 1
  },
  "Slack": {}
}
```

**Minimize Deviations (Max or Sum):**
```json
{
  "Primary": {
    "Method": 2,
    "AggFill": 1000,
    "Aggregate": 2
  },
  "Slack": {}
}
```

> `"Aggregate": 2` applies to **Minimize Deviations Max** only.

---

## Common mutations

Because the table is wide, each parameter is a column name in the SET clause — there is no `Name` or `Value` column.

Set a single SQL-only parameter:
```sql
UPDATE input_parameters
SET StartBalance = '1500000.00'
WHERE RunID = '{run_id}'
```

Set multiple parameters in one statement:
```sql
UPDATE input_parameters
SET IsInfeasible = 'Yes',
    InfeasibilitySlackApproach = 'Balances'
WHERE RunID = '{run_id}'
```

Form-driven parameters are written as a single UPDATE (generated by the app at confirmation):
```sql
UPDATE input_parameters
SET StartPeriod = '461',
    EndPeriod = '1812',
    MainObjectiveFunction = 'Maximize Bank Balance',
    MIPGap = '0.001'
WHERE RunID = '{run_id}'
```

## Note
Form-driven parameters (`StartPeriod`, `EndPeriod`, `MainObjectiveFunction`, `MIPGap`) are written to this table via a single UPDATE generated from the Step 3.3 form values at confirmation — the LLM must not generate SQL for them. SQL-only parameters must be set explicitly via `sql_mutations` if a non-default value is needed.