---
name: hive-optimizer-nl-intent
description: >
  Translates natural language commands into a structured intent for the Hive Global
  Optimizer. Produces executable SQL mutations (sql_mutations) to apply to input tables
  before executing the optimizer. Run configuration (name, description, user, objective,
  duration, mip_gap, timeout, start_period, overhead) is collected separately by the
  application form — the model does NOT output a run_params block.

  Trigger on phrases like: "run the optimizer with OPEX 12M/year", "start from period 461
  for 2 years", "scale performance curves from period 465 to 521 by 20%", "set the
  capital raised in 2027 to 80 million", "change the interest rate on Loan1",
  "update the COGS rate for C1", "what is the deployment capacity for C1 in period 85",
  or any reference to modifying/querying optimizer input data.
---

# Hive Global Optimizer — NL-to-Intent Skill

This skill translates a natural language command into a structured JSON intent that can
be executed against the Hive Global Optimizer system in Microsoft Fabric.

## Your Job

Given a user command, output a JSON object matching the **Output Schema** below.
- Do not execute any query.
- Do not write code beyond the SQL strings in `sql_mutations`.
- Ask clarifying questions by populating `ambiguities` and lowering `confidence`.

---

## Reference Documents

For full table schemas (fields, types, PKs/FKs, validations, business context):
- **Architecture overview**: [`references/schema_overview.md`](references/schema_overview.md)
- **Per-table details**: [`references/tables/<table_name>.md`](references/tables/)
- **Full schema reference**: [`references/schema_reference.md`](references/schema_reference.md)

---

## Data Model Key Points

- **Periods are weekly** (Monday start). `PeriodLabel` format: `YYYY-MM-DD`.
  Period 1 = `2017-06-12`. All tables reference time via `PeriodID`.
- **All run-scoped tables are partitioned by `RunID`** — every SQL mutation on a
  run-scoped table **must** include `WHERE RunID = '{run_id}'`.
  Run-scoped tables: all 14 `input_*` tables with a RunID column, plus all 11 `output_*` tables.
  Reference tables without RunID: `input_portfolios`, `input_customer_groups`,
  `input_cogs_types`, `input_investors`, `input_direct_mail_curves`,
  `input_fix_deployments`, `input_fix_direct_mails`, `input_fix_raises`,
  `input_portfolio_deployments`.

---

## Step 1 — Run configuration is collected by the app (do NOT output it)

**Do not output a `run_params` block.** Run configuration — `name`, `description`,
`user`, `objective_function`, `duration`, `mip_gap`, `timeout_seconds`,
and `start_period` — is collected separately by the application's Run Parameters form.
Your output schema has no `run_params` field; emitting one is a hard failure.

You still need a few of these values to build correct **period-range SQL** in Step 3.
When the user does not state them, use these documented defaults:

| Value | Default for SQL period ranges |
|---|---|
| `start_period` | `461` (PeriodID the run begins at) |
| `duration` | `1351` (number of weekly periods; 1 year = 52 periods) |

### User command → handling

| User says | Handling | Notes |
|---|---|---|
| "OPEX", "overhead", "fixed expenses" | → Generate SQL mutation on `input_portfolios_config.Overhead` in Step 3 | Overhead is a **table value**, not a run parameter |
| "start period 461" / "run for 2 years" / "MIP gap 0.5%" / "timeout 10 min" / "maximize bank balance" | *(no SQL unless it affects a table)* | These are run-config values entered in the app form. Only use `start_period`/`duration` when needed to bound a period range in SQL. |
| "starting in July 2024" applied to a table value | Resolve the period for the SQL `WHERE` clause | See Period Resolution |

> **HARD RULE — OPEX/Overhead routing:** Any user command containing "OPEX", "overhead", or "fixed expenses" **always** requires a SQL mutation targeting `input_portfolios_config.Overhead` (Step 3). It is **never** a run configuration parameter and must **never** produce an empty `sql_mutations`. Emitting `sql_mutations: []` for an OPEX/overhead intent is a hard failure.

---

## Step 2 — Identify target tables and load their schemas

Before writing any SQL, do the following:

1. Read the **Table mapping** and **Special mutations** sections in Step 3 to identify every table the user's command requires modifying.
2. For each identified table, call **Read** on:
   `skills/hive-optimizer-nl-intent/references/tables/<table_name>.md`
   substituting the actual table name (e.g. `input_cogs.md`, `input_investor_capital.md`).
3. From the loaded file, extract: column names and types, primary key fields, foreign key relationships, and any business-context notes.
4. Use that information to write correct `SET` clauses, `WHERE` conditions, and column references in Step 3.

If no table changes are needed, skip to Step 3 and set `sql_mutations` to `[]`.

---

## Step 3 — Populate `sql_mutations` (always required; may be empty)

`sql_mutations` is an array of **executable SQL strings** to apply to input tables
before running the optimizer. Use `[]` if no table changes are needed.

### SQL generation rules

1. **Allowed verbs**: `UPDATE`, `INSERT`, `DELETE` only. No `SELECT` in mutations
   (reads are handled separately).
2. **RunID is mandatory**: Every mutation on a run-scoped table must include
   `WHERE RunID = '{run_id}'`. Use the literal placeholder `'{run_id}'` — never
   guess or invent a UUID.
3. **Allowed tables**: Only target known input tables (see reference tables list above).
   Never target output tables or system tables.
4. **Format**: Write clean, readable SQL. Put each clause on its own line.

### Example valid mutation

```sql
UPDATE input_cogs
SET CogsRate = 0.25
WHERE RunID = '{run_id}'
  AND CustomerGroupID = 'C1'
  AND PeriodID = 85
```

### Table mapping — common intents to tables

| User references | Table | PK fields for WHERE | Notes |
|---|---|---|---|
| loan interest rate, loan terms, principal, repayment | `input_investor_capital` | `InvestorCapitalID` | |
| repayment schedule, payment obligation | `input_investor_repayment_schedule` | `InvestorCapitalID`, `PeriodID`, `PaymentType` | |
| COGS rate, cost of goods sold, underwriting cost | `input_cogs` | `CustomerGroupID`, `CogsID`, `PeriodID`, `PeriodsSinceDeployment` | Default `CogsID = 'ALL'`; see COGS rules below |
| OPEX, overhead, fixed operating expenses | `input_portfolios_config` | `PortfolioID`, `PeriodID` | Field: `Overhead`; see schema_reference.md §input_portfolios_config |
| deployment capacity, capacity limit | `input_customer_capacities` | `CustomerGroupID`, `PeriodID` | |
| performance curves, return rate, repeat return | `input_performance_curves` | `CustomerGroupID`, `PeriodID`, `PeriodsSinceDeployment` | |
| unit margin | *both `input_performance_curves` and `input_cogs`* | — | See Derived Concepts section |
| fixed deployment, committed deployment | `input_fix_deployments` | `CustomerGroupID`, `OriginalPeriodID`, `PeriodID`, `IsRepeat` | |
| fixed raise, exact capital raise amount | `input_fix_raises` | `InvestorCapitalID`, `PeriodID` | No RunID (reference table); field: `Quantity` |
| capital raise upper bound constraint | `input_aggregated_raises` | `FromPeriodID`, `ToPeriodID`, `ConstraintType` | NO `InvestorCapitalID` — applies to all capital combined. Only ask: exact or upper bound? Never ask which investor. |
| aggregated deployment constraint | `input_aggregated_deployments` | `FromPeriodID`, `ToPeriodID` | |
| time periods, period label, calendar date | `input_time_periods` | `PeriodID` | |
| optimizer parameters, start balance | `input_parameters` | — (wide table: one row per RunID, parameter names are column names) | Only SQL-only params; form-driven params are set automatically |

### COGS rules

**CogsID default:** When the user does not specify a COGS type, use `CogsID = 'ALL'` in the WHERE clause — no clarification needed.

**COGS type clarification (when user mentions a specific type):** If the user says a specific COGS type (e.g., "underwriting", "payment processing"), ask which type using human-readable names, then resolve to `CogsID` by looking up `input_cogs_types`. Do not ask if no type is mentioned.

**Customer group rule:**
- If there is only **one customer group**, apply the COGS mutation for that group without asking.
- If there are **multiple customer groups** and none is specified, add an ambiguity question: "Should this COGS change apply to all customer groups equally, or do you want to set different values by group? If different, please specify each group and its value."

---

### Populate `sql_mutation_reasoning` (always required)

After writing `sql_mutations`, populate `sql_mutation_reasoning` with a one-to-two sentence explanation of the mutation decisions. Cover: which table mapping rule was applied, why those columns/values/WHERE conditions were chosen, and any value conversions made. **When `sql_mutations` is `[]`, still explain why no table changes were needed** (e.g. the user only changed run configuration, which is entered in the app's Run Parameters form).

### Special mutations

| User says | Table | Notes |
|---|---|---|
| "scale performance curves from period X to Y by Z%" | `input_performance_curves` | UPDATE multiplying `ReturnRate` and `RepeatReturnRate` by `(1 - Z/100)`; flag scale factor in `ambiguities` |
| capital raise — **exact amount** (optimizer must raise exactly this) | `input_fix_raises` | UPDATE/INSERT `Quantity`; PK is `InvestorCapitalID + PeriodID`; **no RunID** (reference table). Ask: "Which investor should this apply to?" to get the `InvestorCapitalID`. |
| capital raise — **upper bound** (optimizer may raise up to this) | `input_aggregated_raises` | INSERT/UPDATE `AggRaises` with `ConstraintType = 'LessThanOrEqual'`; PK includes RunID. **No `InvestorCapitalID` — do NOT ask which investor.** |
| capital raise — **intent not stated** | *(no SQL yet)* | Ask: "Is this an exact fixed amount the optimizer must raise, or an upper bound it may raise up to?" Then: if exact → also ask which investor; if upper bound → do not ask about investor. |
| "set OPEX / overhead to X" | `input_portfolios_config` | UPDATE `Overhead`; can target all periods (`PeriodID BETWEEN start AND end`) or a specific period; ask if period-level or portfolio-level |

---

## Period Resolution

**Periods are weekly. PeriodLabel = Monday date in YYYY-MM-DD format.**

### Three-tier lookup behavior

| User input | Resolution | `period_resolution_required` |
|---|---|---|
| `YYYY-MM-DD` (exact date) | Floor to containing week: `SELECT PeriodID FROM input_time_periods WHERE RunID = '{run_id}' AND PeriodLabel <= 'YYYY-MM-DD' ORDER BY PeriodLabel DESC LIMIT 1` | `false` |
| `YYYY-MM` (month only) | Default to first week of that month: `WHERE RunID = '{run_id}' AND PeriodLabel >= 'YYYY-MM-01' ORDER BY PeriodLabel ASC LIMIT 1`; state in `plain_english`: "Defaulting to the first week of [Month YYYY]. Let me know if you meant a different week." | `false` |
| `YYYY` (year only) | Cannot resolve without knowing the month — ask clarifying question | `true`, `confidence < 0.80`, populate `ambiguities` with "Which month in [YEAR] did you mean?" |

**Period floor rule**: if a date falls between two PeriodLabels, take the smaller
PeriodID — that is the week containing the date.

**`input_time_periods` lookup**: When a user provides a datetime (any format), you can also look up the matching PeriodID directly from `input_time_periods`:
```sql
SELECT PeriodID FROM input_time_periods
WHERE RunID = '{run_id}'
  AND PeriodLabel = '<user-provided-datetime>'
LIMIT 1
```
Use this pattern when the user provides an exact label that matches `input_time_periods.PeriodLabel`.

---

## Value Granularity Ambiguity

When a user gives a numeric value without a clear time unit, ask:

> "Is [value] a monthly, yearly, or weekly (per-period) amount?"

- **Weekly/per-period** → use directly as-is in the SQL.
- **Monthly or yearly** → follow up with:
  > "How would you like it applied across the month's weeks?"
  > 1. Equally divided across each week of that month (value ÷ number of weeks)
  > 2. Apply only to the first week of the month
  > 3. Apply only to the last week of the month

Each choice produces different `sql_mutations`:
- **Option 1**: Multiple UPDATE statements, one per week of the month, each with `value ÷ week_count`
- **Option 2**: Single UPDATE with `WHERE PeriodID = [first week of month]`
- **Option 3**: Single UPDATE with `WHERE PeriodID = [last week of month]`

Record the distribution choice in `plain_english` and flag it in `ambiguities` until confirmed.

This applies to all table mutations involving numeric values without an explicit time unit.

---

## Derived Concepts

### Unit Margin

**Definition:** `unit margin = vintage return − COGS − 1`

| Component | Table | Field (new customers) | Field (repeat customers) |
|---|---|---|---|
| Vintage return | `input_performance_curves` | `ReturnRate` | `RepeatReturnRate` |
| COGS | `input_cogs` | `CogsRate` | `RepeatCogsRate` |

**When a user asks to modify unit margin:**
1. **Do NOT generate any SQL.** Set `sql_mutations: []` and `confidence < 0.80`.
2. Ask all of the following as separate items in `ambiguities`:
   - "What value should vintage return (`ReturnRate` / `RepeatReturnRate`) be set to?"
   - "What value should COGS (`CogsRate` / `RepeatCogsRate`) be set to? (These two values must satisfy: vintage return − COGS − 1 = requested unit margin.)"
   - "Is this margin for new customers (non-repeats), repeat customers, or a blended average of both?"
3. Only generate SQL once the user has provided specific values for both vintage return and COGS.

---

## Ambiguity Rules

**Format:** Each entry in `ambiguities[]` must be a single plain question or note — no leading number prefix. Separate each ambiguity into its own item — do not combine multiple questions in one string.

Populate `ambiguities[]` and set `confidence < 0.80` when any of these apply:

- **Start period not specified** — always ask: "What start period should the scenario apply from? (Provide a PeriodID integer, or a date/month — I'll look it up in the `input_time_periods` table.)" Do not silently default to 461.
- **Value time unit missing** — user gives a number without specifying weekly/monthly/yearly
  for a table mutation. Ask the clarifying question above.
- **Year-level period** — user gives only a year → set `period_resolution_required: true`
  and ask which month.
- **Performance curve scale** — given as "20%" → note `ReturnRate` and `RepeatReturnRate`
  multiplied by 0.8; flag the conversion.
- **`duration` in years/months** → convert to weekly periods and flag.
- **`objective_function` not specified** → default to `"Maximize Bank Balance"` and note it.
- **COGS type** — `CogsID` defaults to `'ALL'`; no clarification needed unless the user explicitly references a specific COGS type (e.g. "underwriting", "payment processing"). If a type is mentioned, ask: "Which COGS type? Options: Payment Processing, Call Center, Other (Longitudinal); Underwriting, Marketing (CrossSectional)." Then resolve to `CogsID` via `input_cogs_types`.
- **Capital raise — exact vs upper bound** — always ask before generating SQL: "Is this an exact fixed amount the optimizer must raise, or an upper bound it may raise up to?"
  - **Exact** → `input_fix_raises.Quantity` (PK: `InvestorCapitalID + PeriodID`). After confirming exact, ask: "Which investor should this apply to? Please provide the `InvestorCapitalID`." Do not generate SQL until you have it.
  - **Upper bound** → `input_aggregated_raises.AggRaises` with `ConstraintType = 'LessThanOrEqual'`. This table has **no `InvestorCapitalID`** — do NOT ask which investor.
- **Unit margin modification** — never generate SQL directly; ask for vintage return value, COGS value, and whether it applies to new customers, repeat customers, or both. See Derived Concepts section.

---

## Output Schema

```json
{
  "sql_mutations": [
    "UPDATE input_cogs\nSET CogsRate = 0.25\nWHERE RunID = '{run_id}'\n  AND CustomerGroupID = 'C1'\n  AND PeriodID = 85"
  ],
  "sql_mutation_reasoning": "Explanation of why these sql_mutations were generated, or why sql_mutations is empty.",
  "period_resolution_required": false,
  "period_label": null,
  "confidence": 0.95,
  "ambiguities": [],
  "plain_english": "Human-readable summary of what this intent will do."
}
```

### Field rules

- **No `run_params`**: do not emit a `run_params` field. Run configuration is collected by the app form.
- **`sql_mutations`**: always present; `[]` when no table changes are needed. Each string is
  a complete SQL statement with `'{run_id}'` placeholder. Only `UPDATE`/`INSERT`/`DELETE`.
  Every run-scoped table mutation must include `WHERE RunID = '{run_id}'`.
- **`sql_mutation_reasoning`**: always present. One or two sentences explaining the table
  mapping decision, column/value/WHERE choices, and any conversions applied. When
  `sql_mutations` is `[]`, explain why no table changes are needed.
- **`period_resolution_required`**: `true` only when a year-only label was given and the
  agent must ask a clarifying question. `false` for `YYYY-MM-DD` (exact) and `YYYY-MM`
  (defaults to first week).
- **`period_label`**: `YYYY` when `period_resolution_required` is `true`. `null` otherwise.
- **`confidence`**: float 0–1. Below 0.80 must have non-empty `ambiguities`.
- **`ambiguities`**: empty only when `confidence ≥ 0.80`.
- **`plain_english`**: always include. One or two sentences a non-technical user can read.

---

## Examples

**Command:** "Run the optimizer from period 461 for 2 years with a 0.5% MIP gap."
```json
{
  "sql_mutations": [],
  "sql_mutation_reasoning": "No table mutations required — the user only specified run configuration (start period, duration, and MIP gap), which is entered in the app's Run Parameters form, not in any input table. No input table data needs to change.",
  "period_resolution_required": false,
  "period_label": null,
  "confidence": 0.95,
  "ambiguities": [],
  "plain_english": "No input table changes needed — this command only sets run configuration (start period 461, ~2 year duration, 0.5% MIP gap), which you enter in the Run Parameters form."
}
```

---

**Command:** "OPEX is 12 million per year, start from period 461."
```json
{
  "sql_mutations": [
    "UPDATE input_portfolios_config\nSET Overhead = 230769.23\nWHERE RunID = '{run_id}'\n  AND PeriodID BETWEEN 461 AND (461 + 1351)"
  ],
  "sql_mutation_reasoning": "User said 'OPEX is 12 million per year' → overhead goes to input_portfolios_config.Overhead. Annual $12M converted to weekly: 12,000,000 / 52 ≈ 230,769.23. Applied across the run range using start_period 461 and the default duration 1351.",
  "period_resolution_required": false,
  "period_label": null,
  "confidence": 0.80,
  "ambiguities": [
    "Annual OPEX of $12M converted to weekly: 12,000,000 / 52 ≈ 230,769.23 per period. Confirm this unit conversion.",
    "Applied Overhead to all periods from 461 to 461+1351 (default duration). Let me know if you intended a specific period range."
  ],
  "plain_english": "Set the weekly overhead in input_portfolios_config to ~$230,769 (converted from $12M annual OPEX) for all periods starting at period 461."
}
```

---

**Command:** "Change the interest rate on Loan1 to 1.5%."
```json
{
  "sql_mutations": [
    "UPDATE input_investor_capital\nSET InterestRate = 0.015\nWHERE RunID = '{run_id}'\n  AND InvestorCapitalID = 'Loan1'"
  ],
  "sql_mutation_reasoning": "User said 'change interest rate on Loan1 to 1.5%' → mapped to input_investor_capital.InterestRate per the loan/interest-rate table mapping. InvestorCapitalID = 'Loan1' comes directly from the user. Value 1.5% assumed as decimal 0.015 — flagged in ambiguities.",
  "period_resolution_required": false,
  "period_label": null,
  "confidence": 0.75,
  "ambiguities": [
    "Confirm whether InterestRate is stored as a decimal fraction (0.015) or a percentage (1.5) in input_investor_capital."
  ],
  "plain_english": "Update the interest rate for Loan1 to 1.5% in input_investor_capital, then run the optimizer with default parameters."
}
```

---

**Command:** "Update the underwriting COGS rate for C1 to 25% starting July 2024."
```json
{
  "sql_mutations": [
    "UPDATE input_cogs\nSET CogsRate = 0.25\nWHERE RunID = '{run_id}'\n  AND CustomerGroupID = 'C1'\n  AND PeriodID = (SELECT PeriodID FROM input_time_periods WHERE RunID = '{run_id}' AND PeriodLabel >= '2024-07-01' ORDER BY PeriodLabel ASC LIMIT 1)"
  ],
  "sql_mutation_reasoning": "User said 'underwriting COGS rate for C1 to 25% starting July 2024' → mapped to input_cogs.CogsRate per the COGS table mapping. CustomerGroupID = 'C1' from user. Month '2024-07' defaulted to first week of July via period floor subquery. CogsTypeID not specified — flagged in ambiguities.",
  "period_resolution_required": false,
  "period_label": null,
  "confidence": 0.75,
  "ambiguities": [
    "Month '2024-07' defaulted to the first week of July 2024. If a different week was intended, please specify the exact date.",
    "input_cogs has multiple COGS types; 'underwriting' maps to a specific CogsTypeID — confirm the exact CogsTypeID."
  ],
  "plain_english": "Update the underwriting COGS rate for customer group C1 to 25%, applying to the first week of July 2024. Confirm the CogsTypeID for underwriting."
}
```

---

**Command:** "Set the capital raised in 2027 to 80 million."
```json
{
  "sql_mutations": [],
  "sql_mutation_reasoning": "No SQL generated yet — the target period cannot be resolved without knowing the month in 2027, and the value granularity ($80M yearly/monthly/weekly) is unconfirmed. Will generate an INSERT into input_aggregated_raises once both are clarified.",
  "period_resolution_required": true,
  "period_label": "2027",
  "confidence": 0.60,
  "ambiguities": [
    "Year '2027' cannot be resolved to a PeriodID without knowing the month. Which month in 2027 did you mean?",
    "Is $80M the total for the year, a monthly amount, or a weekly amount? If monthly or yearly, how should it be distributed across weeks?"
  ],
  "plain_english": "Cannot fully generate the SQL until the target month in 2027 is confirmed and the value granularity (yearly/monthly/weekly) is clarified."
}
```

---

## Evaluation Rubric

Score each response out of **8 points**. Pass = 7–8; acceptable = 5–6; fail = < 5.

| # | Criterion | Points | How to score |
|---|-----------|--------|--------------|
| 1 | `sql_mutations` SQL verb correct | 1 | +1 if only UPDATE/INSERT/DELETE used; 0 if SELECT appears or verb is wrong |
| 2 | `sql_mutations` table correct | 1 | +1 if SQL targets the right table; 0 if wrong table |
| 3 | `sql_mutations` SET / values correct | 2 | +1 per correct field=value pair in the SQL (max 2); −1 per hallucinated column |
| 4 | `sql_mutations` WHERE correct | 1 | +1 if RunID placeholder present on run-scoped tables and PK columns are correct; 0 if missing |
| 5 | `period_resolution_required` accurate | 1 | +1 set to `true` only when year-level; `false` for exact or month-level (with default note) |
| 6 | `confidence` calibrated | 1 | +1 if `ambiguities` non-empty ↔ `confidence < 0.80`, and empty ↔ `≥ 0.80` |
| 7 | `ambiguities` completeness | 1 | +1 if all unit conversions, assumptions, unresolved fields flagged (including value granularity when missing) |
