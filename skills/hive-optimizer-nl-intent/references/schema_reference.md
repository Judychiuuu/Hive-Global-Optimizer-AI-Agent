# Model Schema Documentation - Global Optimizer
**Generated:** 2026-01-20 23:07:10  
**Project:** Global Optimizer  
**Purpose:** Comprehensive documentation for all input and output tables in the Global Optimizer model

---

## Executive Summary

The **Global Optimizer** is a Mixed Integer Programming (MIP) model designed to maximize bank balance or minimize the crossover point by optimizing:
- **Capital Deployment Decisions**: How much to lend to each customer segment in each period
- **Capital Raising Decisions**: When and how much to raise from investor sources
- **Cost Management**: Balancing deployment costs (COGS) against revenue generation

### Objective Functions
1. **Maximize Bank Balance**: Maximize cash position at the end of the simulation period
2. **Minimize Crossover Point**: Minimize the first period where assets exceed liabilities

### Key Constraints
- Investor debt service obligations (interest + principal repayments)
- Customer deployment capacities (demand saturation limits)
- Portfolio-level deployment and fundraising targets
- Cash flow feasibility (cannot overdraw bank balance)
- Fixed commitments (pre-committed deployments and raises)

---


---

## 🔑 RunID Architecture

Every optimization run is identified by a unique `RunID` (UUID string). Tables are **partitioned by RunID** — each run copies base data from a prior run, assigns the new `RunID`, then applies scenario-specific modifications to those rows only.

**Tables WITH RunID** (all queries must filter `WHERE RunID = '{run_id}'`):
- All 14 run-specific input tables (parameters, time_periods, periods_config, portfolios_config, customer_capacities, net_new_capacities, aggregated_deployments, aggregated_raises, relative_deployments, performance_curves, repeats_distribution, cogs, investor_capital, investor_repayment_schedule)
- All 11 output tables (results are written per RunID and cleared before each new solve)

**Reference tables WITHOUT RunID** (shared across all runs):
- `input_portfolios`, `input_customer_groups`, `input_cogs_types`, `input_investors`, `input_direct_mail_curves`, `input_fix_deployments`, `input_fix_direct_mails`, `input_fix_raises`, `input_portfolio_deployments`

**RunID generation:** `RunID` is always created by the `DE_NB_CopyRun` notebook (called from `run_optimizer.ipynb`). It is never manually assigned.

---

## ⚙️ Model Assumptions & Configuration

### Time Period Handling (Weekly Model)

**Weekly Periods:**
- Simulation periods are **weekly** (Monday start)
- **Period 1** is defined as **2017-07-03** (first Monday of July 2017)
- `input_time_periods` assigns sequential PeriodIDs for each week
- PeriodLabel stores the **Monday date** of each week in YYYY-MM-DD format

**Example Period Mapping:**
```
PeriodID | PeriodLabel
---------|------------
1        | 2017-07-03
2        | 2017-07-10
3        | 2017-07-17
...      | ...
```

**Period lookup rule:** If a user supplies a date that falls mid-week, use the PeriodID whose PeriodLabel is ≤ the given date (i.e., take the Monday that starts the containing week):
```sql
SELECT PeriodID FROM input_time_periods
WHERE RunID = '{run_id}' AND PeriodLabel <= 'YYYY-MM-DD'
ORDER BY PeriodLabel DESC
LIMIT 1
```

---

### 🏁 Starting Balance Logic

To initialize each simulation run with an accurate starting balance:

**Simulation Start Rule:**
- Each simulation begins at the start of the target week
- StartPeriod corresponds to the PeriodID for the first week of the simulation window

**Starting Balance Sourcing Rule:**
- Starting balance is pulled from the **last day of the previous week** (i.e., the Sunday before StartPeriod)
- Source table: `month_end_actuals`
- Source field: `Balance` where `PortfolioID = 'All'`

**Example Scenarios:**

| Simulation Start Week | StartPeriod | Starting Balance Source |
|----------------------|-------------|------------------------|
| Week of 2025-12-01 | PeriodID for 2025-12-01 | `month_end_actuals.Balance` WHERE `PeriodLabel = '2025-11-30'` AND `PortfolioID = 'All'` |
| Week of 2026-01-05 | PeriodID for 2026-01-05 | `month_end_actuals.Balance` WHERE `PeriodLabel = '2026-01-04'` AND `PortfolioID = 'All'` |

**Critical Implementation Notes:**
1. The `StartBalance` value in `input_parameters` must match the balance from `month_end_actuals` for the last day before the start week
2. The `StartPeriod` in `input_parameters` must be set to the PeriodID corresponding to the first week of the simulation
3. This ensures continuity between historical actuals and forward-looking optimization

---

## Table of Contents

### Input Tables (23 tables)
1. [input_aggregated_deployments](#input-aggregated-deployments)
2. [input_aggregated_raises](#input-aggregated-raises)
3. [input_cogs](#input-cogs)
4. [input_cogs_types](#input-cogs-types)
5. [input_customer_capacities](#input-customer-capacities)
6. [input_customer_groups](#input-customer-groups)
7. [input_direct_mail_curves](#input-direct-mail-curves)
8. [input_fix_deployments](#input-fix-deployments)
9. [input_fix_direct_mails](#input-fix-direct-mails)
10. [input_fix_raises](#input-fix-raises)
11. [input_investor_capital](#input-investor-capital)
12. [input_investors](#input-investors)
13. [input_investor_repayment_schedule](#input-investor-repayment-schedule)
14. [input_net_new_capacities](#input-net-new-capacities)
15. [input_parameters](#input-parameters)
16. [input_performance_curves](#input-performance-curves)
17. [input_periods_config](#input-periods-config)
18. [input_portfolios](#input-portfolios)
19. [input_portfolio_deployments](#input-portfolio-deployments)
20. [input_portfolios_config](#input-portfolios-config)
21. [input_relative_deployments](#input-relative-deployments)
22. [input_repeats_distribution](#input-repeats-distribution)
23. [input_time_periods](#input-time-periods)

### Output Tables (11 tables)
1. [output_aggregated_deployments_slacks](#output-aggregated-deployments-slacks)
2. [output_customer_deployments_slacks](#output-customer-deployments-slacks)
3. [output_deployments_slacks](#output-deployments-slacks)
4. [output_portfolio_deployments_slacks](#output-portfolio-deployments-slacks)
5. [output_kpis](#output-kpis)
6. [output_ledger](#output-ledger)
7. [output_ledger_pivot](#output-ledger-pivot)
8. [output_balances](#output-balances)
9. [output_financial](#output-financial)
10. [output_raises_slacks](#output-raises-slacks)
11. [output_balances_slacks](#output-balances-slacks)

---

# Input Tables

## input_aggregated_deployments

### Overview
**Type:** Input  
**Row Count Schema Fields:** 3

Aggregate deployment targets or limits across multiple customer groups or time periods.

---

### Grain
**Primary Key:** `RunID + FromPeriodID + ToPeriodID`

One row per RunID + aggregation grouping

---

### Relationships
- **FromPeriodID** → `[time_periods.PeriodID]`
- **ToPeriodID** → `[time_periods.PeriodID]`

---

### Business Context

Similar to aggregated_raises but for deployment decisions. Enables constraints like "Total deployments in 2025 must be at least $X" or "Maximum $Y deployed to high-risk segments per quarter".

**Update Cadence:** Set based on business strategy and risk appetite

---

### Fields

| Field | Type | Required | Validation | Description | PII |
|------|------|----------|------------|-------------|-----|
| `RunID` | Text/String | ✓ Required | None | 🔑 PK | No |
| `FromPeriodID` | Integer | ✓ Required | FromPeriodID + 1 <= ToPeriodID | 🔑 PK 🔗 FK → [time_periods.PeriodID] | No |
| `ToPeriodID` | Integer | ✓ Required | None | 🔑 PK 🔗 FK → [time_periods.PeriodID] | No |
| `AggDeploymentCapacity` | Decimal/Float | ✓ Required | >= 0 | — | No |

---


---

### Example Queries

```sql
-- Basic table exploration
SELECT *
FROM input_aggregated_deployments
LIMIT 10;

-- Row count and data coverage
SELECT COUNT(*) as row_count
FROM input_aggregated_deployments
WHERE RunID = '{run_id}';
```

---

## input_aggregated_raises

### Overview
**Type:** Input  
**Row Count Schema Fields:** 4

Aggregate capital raise targets or limits across multiple investors or time periods.

---

### Grain
**Primary Key:** `RunID + FromPeriodID + ToPeriodID + ConstraintType`

One row per RunID + aggregation grouping

---

### Relationships
- **FromPeriodID** → `[time_periods.PeriodID]`
- **ToPeriodID** → `[time_periods.PeriodID]`

---

### Business Context

Allows imposing constraints like "Total capital raised in Q1 cannot exceed $X" or "Minimum $Y must be raised from investors in fiscal year". Provides strategic control over the overall fundraising plan.

**Update Cadence:** Set based on fundraising strategy

---

### Fields

| Field | Type | Required | Validation | Description | PII |
|------|------|----------|------------|-------------|-----|
| `RunID` | Text/String | ✓ Required | None | 🔑 PK | No |
| `FromPeriodID` | Integer | ✓ Required | FromPeriodID <= ToPeriodID | 🔑 PK 🔗 FK → [time_periods.PeriodID] | No |
| `ToPeriodID` | Integer | ✓ Required | None | 🔑 PK 🔗 FK → [time_periods.PeriodID] | No |
| `AggRaises` | Decimal/Float | ✓ Required | >= 0 | Maximum/total capital that can be raised within [FromPeriodID, ToPeriodID] | No |
| `ConstraintType` | Text/String | ✓ Required | Must be one of 'LessThanOrEqualTo' or 'EqualTo'. | 🔑 PK | No |

---


---

### Example Queries

```sql
-- Basic table exploration
SELECT *
FROM input_aggregated_raises
LIMIT 10;

-- Row count and data coverage
SELECT COUNT(*) as row_count
FROM input_aggregated_raises
WHERE RunID = '{run_id}';
```

---

## input_cogs

### Overview
**Type:** Input  
**Row Count Schema Fields:** 7

Cost of Goods Sold (lending costs) per funded dollar, by customer group, COGS type, and period.

---

### Grain
**Primary Key:** `RunID + CustomerGroupID + CogsTypeID + PeriodID + PeriodsSinceDeployment`

One row per RunID + CustomerGroupID + CogsTypeID + PeriodID + PeriodsSinceDeployment

---

### Relationships
- **CustomerGroupID** → `[customer_groups.CustomerGroupID]`
- **CogsTypeID** → `[cogs_types.CogsTypeID]`
- **PeriodID** → `[time_periods.PeriodID]`

---

### Business Context

COGS represents the **cost per funded $1** which, when multiplied by deployment amount, yields total costs. There are two types:

**Longitudinal COGS** - Variable costs that scale with deployments:
- Payment Processing: Transaction fees for borrower payments
- Call Center: Customer service costs per loan
- Other: Additional servicing expenses

**Cross-sectional COGS** - Fixed period costs:
- Marketing: Customer acquisition costs (especially Direct Mail)
- Underwriting: Credit evaluation and loan origination

The optimizer balances deployment revenue against these costs to maximize profitability.

**Update Cadence:** Monthly or quarterly based on updated cost projections

---

### Fields

| Field | Type | Required | Validation | Description | PII |
|------|------|----------|------------|-------------|-----|
| `RunID` | Text/String | ✓ Required | None | 🔑 PK | No |
| `CustomerGroupID` | Text/String | ✓ Required | None | 🔑 PK 🔗 FK → [customer_groups.CustomerGroupID] | No |
| `CogsTypeID` | Text/String | ✓ Required | None | 🔑 PK 🔗 FK → [cogs_types.CogsTypeID] | No |
| `PeriodID` | Integer | ✓ Required | None | 🔑 PK 🔗 FK → [time_periods.PeriodID] | No |
| `PeriodsSinceDeployment` | Integer | ✓ Required | >= 0 | 🔑 PK | No |
| `CogsLabel` | Text/String | ✓ Required | Must be one of: 'Longitudinal', 'CrossSectional' | — | No |
| `CogsRate` | Decimal/Float | ✓ Required | >= 0 | — | No |
| `RepeatCogsRate` | Decimal/Float | ✓ Required | >= 0 | — | No |

---

### Field Details

**CogsTypeID Categories:**

**Longitudinal COGS** (variable, scale with deployments):
- **Payment Processing**: Transaction fees per borrower payment
- **Call Center**: Customer service costs per active loan
- **Other**: Additional servicing/operational costs

**Cross-sectional COGS** (fixed per period):
- **Underwriting**: Credit evaluation and loan origination costs
- **Marketing**: Customer acquisition costs (especially Direct Mail campaigns)

**COGSRate:**
- Cost per funded dollar (multiply by deployment amount for total cost)
- Example: COGSRate=0.15 means $0.15 cost per $1.00 deployed
- Varies by customer group and period (reflects different segment economics)

**Cost Structure:**
```
Total COGS = (Deployment × Longitudinal COGS Rate) + Cross-sectional COGS
```

**Optimizer Impact:**
- Deployment decisions must balance return rates against COGS
- Marketing COGS investments create future deployment capacity (via net_new_capacities)
- High-COGS segments need higher returns to be economically viable


---

### Example Queries

```sql
-- Basic table exploration
SELECT *
FROM input_cogs
LIMIT 10;

-- Row count and data coverage
SELECT COUNT(*) as row_count
FROM input_cogs
WHERE RunID = '{run_id}';

-- Temporal coverage check
SELECT 
    MIN(PeriodID) as earliest_period,
    MAX(PeriodID) as latest_period,
    COUNT(DISTINCT PeriodID) as period_count
FROM input_cogs
WHERE RunID = '{run_id}';

-- Customer group breakdown
SELECT 
    CustomerGroupID,
    COUNT(*) as record_count
FROM input_cogs
WHERE RunID = '{run_id}'
GROUP BY CustomerGroupID
ORDER BY record_count DESC;
```

---

## input_cogs_types

### Overview
**Type:** Input  
**Row Count Schema Fields:** 3

Categorizes different types of Cost of Goods Sold (COGS) used in the model.

---

### Grain
**Primary Key:** `CogsTypeID`

One row per COGS type category

---

### Relationships
- No foreign key relationships defined in schema

---

### Business Context

COGS Types fall into two categories:
- **Longitudinal COGS**: Variable costs that scale with deployments (payment processing, call center, other servicing costs)
- **Cross-sectional COGS**: Fixed period costs for customer acquisition (marketing, underwriting)

This taxonomy feeds into input_cogs table for actual cost values per customer group.

**Update Cadence:** Rarely changes; stable taxonomy

---

### Fields

| Field | Type | Required | Validation | Description | PII |
|------|------|----------|------------|-------------|-----|
| `CogsTypeID` | Text/String | ✓ Required | None | 🔑 PK | No |
| `CogsTypeName` | Text/String | ✓ Required | Must be one of: 'Longitudinal', 'CrossSectional' | — | No |
| `CogsLabel` | Text/String | ✓ Required | None | — | No |

---


---

### Example Queries

```sql
-- Basic table exploration
SELECT *
FROM input_cogs_types
LIMIT 10;

-- Row count and data coverage
SELECT COUNT(*) as row_count
FROM input_cogs_types;
```

---

## input_customer_capacities

### Overview
**Type:** Input  
**Row Count Schema Fields:** 3

Maximum deployment capacity available for each customer group per period, representing demand saturation constraints.

---

### Grain
**Primary Key:** `RunID + CustomerGroupID + PeriodID`

One row per RunID + CustomerGroupID + PeriodID

---

### Relationships
- **CustomerGroupID** → `[customer_groups.CustomerGroupID]`
- **PeriodID** → `[time_periods.PeriodID]`

---

### Business Context

Capacity constraints prevent unrealistic deployment levels. These limits reflect:
- **Borrower Demand**: Finite qualified applicants per period
- **Underwriting Capacity**: Processing bandwidth limitations  
- **Credit Policy**: Risk management controls on segment exposure
- **Marketing Budget**: Acquisition channel capacity (especially Direct Mail)

Without capacity constraints, the optimizer would deploy infinite capital to high-return segments.

**Update Cadence:** Updated monthly/quarterly based on demand forecasts and credit policy

---

### Fields

| Field | Type | Required | Validation | Description | PII |
|------|------|----------|------------|-------------|-----|
| `RunID` | Text/String | ✓ Required | None | 🔑 PK | No |
| `CustomerGroupID` | Text/String | ✓ Required | None | 🔑 PK 🔗 FK → [customer_groups.CustomerGroupID] | No |
| `PeriodID` | Integer | ✓ Required | None | 🔑 PK 🔗 FK → [time_periods.PeriodID] | No |
| `DeploymentCapacity` | Decimal/Float | ✓ Required | >= 0 | — | No |

---

### Field Details

**CustomerCapacity:**
- Maximum deployment amount in period for this customer group
- Represents real-world demand saturation and underwriting limits
- Prevents unrealistic deployment levels in high-return segments

**Capacity Drivers:**
1. **Borrower Demand**: Finite qualified applicants per period
2. **Underwriting Bandwidth**: Processing capacity constraints
3. **Credit Policy**: Risk management exposure limits
4. **Marketing Budget**: Acquisition channel capacity (especially Direct Mail)

**Seasonal Patterns:**
- Capacity varies by PeriodID to reflect seasonality
- Example: Lower capacity in Q4 due to holiday season
- Higher capacity during tax refund season (Q1)

**Optimizer Behavior:**
- Without capacity constraints, model would deploy infinite capital to best-performing segments
- Capacity scarcity forces strategic timing and allocation decisions
- Marketing investments can expand future capacity (see net_new_capacities)


---

### Example Queries

```sql
-- Basic table exploration
SELECT *
FROM input_customer_capacities
LIMIT 10;

-- Row count and data coverage
SELECT COUNT(*) as row_count
FROM input_customer_capacities
WHERE RunID = '{run_id}';

-- Temporal coverage check
SELECT 
    MIN(PeriodID) as earliest_period,
    MAX(PeriodID) as latest_period,
    COUNT(DISTINCT PeriodID) as period_count
FROM input_customer_capacities
WHERE RunID = '{run_id}';

-- Customer group breakdown
SELECT 
    CustomerGroupID,
    COUNT(*) as record_count
FROM input_customer_capacities
WHERE RunID = '{run_id}'
GROUP BY CustomerGroupID
ORDER BY record_count DESC;
```

---

## input_customer_groups

### Overview
**Type:** Input  
**Row Count Schema Fields:** 4

Defines customer segments used to model expected COGS, performance, and deployment capacity by group characteristics.

---

### Grain
**Primary Key:** `CustomerGroupID`

One row per unique customer segment

---

### Relationships
- **PortfolioID** → `[portfolios.PortfolioID]`

---

### Business Context

Customer Groups allow the optimizer to make nuanced decisions across segments with different:
- **Marketing Channels**: Direct Mail vs. other acquisition channels
- **Risk Levels**: Credit quality segments with varying performance curves
- **Economics**: Different COGS, return rates, and deployment capacities per group

The optimizer can strategically allocate capital to higher-performing segments.

**Update Cadence:** Stable; updated when new customer segments are created or segmentation logic changes

---

### Fields

| Field | Type | Required | Validation | Description | PII |
|------|------|----------|------------|-------------|-----|
| `CustomerGroupID` | Text/String | ✓ Required | None | 🔑 PK | No |
| `CustomerGroupName` | Text/String | ✓ Required | None | — | Possible |
| `CustomerGroupType` | Text/String | ✓ Required | Must be one of: 'Not Direct Mail', 'Direct Mail' | — | No |
| `PortfolioID` | Text/String | ✓ Required | None | 🔗 FK → [portfolios.PortfolioID] | No |

---


---

### Example Queries

```sql
-- Basic table exploration
SELECT *
FROM input_customer_groups
LIMIT 10;

-- Row count and data coverage
SELECT COUNT(*) as row_count
FROM input_customer_groups;

-- Customer group breakdown
SELECT 
    CustomerGroupID,
    COUNT(*) as record_count
FROM input_customer_groups
GROUP BY CustomerGroupID
ORDER BY record_count DESC;
```

---

## input_direct_mail_curves

### Overview
**Type:** Input  
**Row Count Schema Fields:** 4

Defines the rate at which direct mail COGS investments convert into customer deployments over time, by customer group and period.

---

### Grain
**Primary Key:** `CustomerGroupID + PeriodID + PeriodsSinceCogs`

One row per customer group, period, and number of periods elapsed since the direct mail COGS was incurred.

---

### Relationships
- **CustomerGroupID** → `[customer_groups.CustomerGroupID]`
- **PeriodID** → `[time_periods.PeriodID]`

---

### Business Context

Direct mail campaigns require upfront COGS spend (recorded in `input_fix_direct_mails`). This table captures the deployment response curve — how many new borrowers are acquired per dollar spent, in each period after the campaign. The `PeriodsSinceCogs` dimension models the lag between marketing expenditure and realized deployment capacity. The optimizer uses this curve to trade off current marketing spend against future deployment opportunities.

**Update Cadence:** Updated based on historical direct mail campaign response analysis

---

### Fields

| Field | Type | Required | Validation | Description | PII |
|------|------|----------|------------|-------------|-----|
| `CustomerGroupID` | Text/String | ✓ Required | None | 🔑 PK 🔗 FK → [customer_groups.CustomerGroupID] | No |
| `PeriodID` | Integer | ✓ Required | None | 🔑 PK 🔗 FK → [time_periods.PeriodID] | No |
| `PeriodsSinceCogs` | Integer | ✓ Required | >= 0 | 🔑 PK | No |
| `DeploymentRate` | Decimal/Float | ✓ Required | >= 0 | — | No |

---


---

### Example Queries

```sql
-- Basic table exploration
SELECT *
FROM input_direct_mail_curves
LIMIT 10;

-- Row count and data coverage
SELECT COUNT(*) as row_count
FROM input_direct_mail_curves;

-- Temporal coverage check
SELECT 
    MIN(PeriodID) as earliest_period,
    MAX(PeriodID) as latest_period,
    COUNT(DISTINCT PeriodID) as period_count
FROM input_direct_mail_curves;

-- Customer group breakdown
SELECT 
    CustomerGroupID,
    COUNT(*) as record_count
FROM input_direct_mail_curves
GROUP BY CustomerGroupID
ORDER BY record_count DESC;
```

---

## input_fix_deployments

### Overview
**Type:** Input  
**Row Count Schema Fields:** 5

Pre-committed deployments that must be honored by the optimizer (not decision variables).

---

### Grain
**Primary Key:** `CustomerGroupID + OriginalPeriodID + PeriodID + IsRepeat`

One row per CustomerGroupID + PeriodID with fixed deployment

---

### Relationships
- **CustomerGroupID** → `[customer_groups.CustomerGroupID]`
- **OriginalPeriodID** → `[time_periods.PeriodID]`
- **PeriodID** → `[time_periods.PeriodID]`

---

### Business Context

Fixed deployments are hard constraints representing:
- **Existing Pipeline**: Approved loans awaiting funding
- **Contractual Obligations**: Pre-committed capital deployment agreements
- **Historical Actuals**: Past deployments in the model's lookback window

The optimizer treats these as givens and optimizes only the remaining discretionary capital.

**Update Cadence:** Updated when new commitments are made or existing deployments are executed

---

### Fields

| Field | Type | Required | Validation | Description | PII |
|------|------|----------|------------|-------------|-----|
| `CustomerGroupID` | Text/String | ✓ Required | None | 🔑 PK 🔗 FK → [customer_groups.CustomerGroupID] | No |
| `OriginalPeriodID` | Integer | ✓ Required | OriginalPeriodID <= PeriodID when IsRepeat = 'Yes' | 🔑 PK 🔗 FK → [time_periods.PeriodID] | No |
| `PeriodID` | Integer | ✓ Required | None | 🔑 PK 🔗 FK → [time_periods.PeriodID] | No |
| `IsRepeat` | Text/String | ✓ Required | Must be one of: 'Yes', 'No' | 🔑 PK | No |
| `Quantity` | Decimal/Float | ✓ Required | >= 0 | — | No |

---


---

### Example Queries

```sql
-- Basic table exploration
SELECT *
FROM input_fix_deployments
LIMIT 10;

-- Row count and data coverage
SELECT COUNT(*) as row_count
FROM input_fix_deployments;

-- Temporal coverage check
SELECT 
    MIN(PeriodID) as earliest_period,
    MAX(PeriodID) as latest_period,
    COUNT(DISTINCT PeriodID) as period_count
FROM input_fix_deployments;

-- Customer group breakdown
SELECT 
    CustomerGroupID,
    COUNT(*) as record_count
FROM input_fix_deployments
GROUP BY CustomerGroupID
ORDER BY record_count DESC;
```

---

## input_fix_direct_mails

### Overview
**Type:** Input  
**Row Count Schema Fields:** 3

Pre-committed direct mail COGS payments that must be included in the simulation as fixed costs.

---

### Grain
**Primary Key:** `CustomerGroupID + PeriodID`

One row per customer group and period with a fixed direct mail COGS payment.

---

### Relationships
- **CustomerGroupID** → `[customer_groups.CustomerGroupID]`
- **PeriodID** → `[time_periods.PeriodID]`

---

### Business Context

Records scheduled or already-contracted direct mail campaign costs for a specific customer group and period. These are treated as hard, non-discretionary obligations by the optimizer — they cannot be avoided. The corresponding deployment uplift from this spend is modeled in `input_direct_mail_curves`.

**Update Cadence:** Updated when new direct mail campaigns are scheduled or contracted

---

### Fields

| Field | Type | Required | Validation | Description | PII |
|------|------|----------|------------|-------------|-----|
| `CustomerGroupID` | Text/String | ✓ Required | None | 🔑 PK 🔗 FK → [customer_groups.CustomerGroupID] | No |
| `PeriodID` | Integer | ✓ Required | None | 🔑 PK 🔗 FK → [time_periods.PeriodID] | No |
| `CogsPayment` | Decimal/Float | ✓ Required | >= 0 | — | No |

---


---

### Example Queries

```sql
-- Basic table exploration
SELECT *
FROM input_fix_direct_mails
LIMIT 10;

-- Row count and data coverage
SELECT COUNT(*) as row_count
FROM input_fix_direct_mails;

-- Temporal coverage check
SELECT 
    MIN(PeriodID) as earliest_period,
    MAX(PeriodID) as latest_period,
    COUNT(DISTINCT PeriodID) as period_count
FROM input_fix_direct_mails;

-- Customer group breakdown
SELECT 
    CustomerGroupID,
    COUNT(*) as record_count
FROM input_fix_direct_mails
GROUP BY CustomerGroupID
ORDER BY record_count DESC;
```

---

## input_fix_raises

### Overview
**Type:** Input  
**Row Count Schema Fields:** 3

Pre-committed capital raises (debt issuance) that the optimizer must include in the plan.

---

### Grain
**Primary Key:** `InvestorCapitalID + PeriodID`

One row per InvestorCapitalID + PeriodID with scheduled raise

---

### Relationships
- **InvestorCapitalID** → `[investor_capital.InvestorCapitalID]`
- **PeriodID** → `[time_periods.PeriodID]`

---

### Business Context

Fixed raises are capital inflows already committed or contracted. The optimizer must include these and their associated repayment obligations, treating them as givens rather than decision variables.

**Update Cadence:** Updated when new capital commitments are made

---

### Fields

| Field | Type | Required | Validation | Description | PII |
|------|------|----------|------------|-------------|-----|
| `InvestorCapitalID` | Text/String | ✓ Required | None | 🔑 PK 🔗 FK → [investor_capital.InvestorCapitalID] | No |
| `PeriodID` | Integer | ✓ Required | None | 🔑 PK 🔗 FK → [time_periods.PeriodID] | No |
| `Quantity` | Decimal/Float | ✓ Required | >= 0 | — | No |

---


---

### Example Queries

```sql
-- Basic table exploration
SELECT *
FROM input_fix_raises
LIMIT 10;

-- Row count and data coverage
SELECT COUNT(*) as row_count
FROM input_fix_raises;

-- Temporal coverage check
SELECT 
    MIN(PeriodID) as earliest_period,
    MAX(PeriodID) as latest_period,
    COUNT(DISTINCT PeriodID) as period_count
FROM input_fix_raises;
```

---

## input_investor_capital

### Overview
**Type:** Input  
**Row Count Schema Fields:** 11

Tracks loan financing terms for each capital raise from investors, including interest rates, repayment frequency, and principal deadlines.

---

### Grain
**Primary Key:** `RunID + InvestorCapitalID`

One row per RunID + loan/capital raise from an investor

---

### Relationships
- **InvestorID** → `[investors.InvestorID]`

---

### Business Context

Critical input for cash flow modeling. Each row represents a loan with specific terms:
- **Interest Rate**: Per-period interest percentage
- **Interest Type**: Simple vs. compound interest calculations  
- **Repayment Frequency**: When interest payments are due (e.g., quarterly)
- **Principal Deadline**: When the full loan amount must be repaid

The optimizer must ensure sufficient cash flows to meet these obligations while maximizing deployment returns.

**Update Cadence:** Updated when new capital is raised or loan terms are modified

---

### Fields

| Field | Type | Required | Validation | Description | PII |
|------|------|----------|------------|-------------|-----|
| `RunID` | Text/String | ✓ Required | None | 🔑 PK | No |
| `InvestorCapitalID` | Text/String | ✓ Required | None | 🔑 PK | No |
| `InvestorCapitalName` | Text/String | ✓ Required | None | — | Possible |
| `InvestorID` | Text/String | ✓ Required | None | 🔗 FK → [investors.InvestorID] | No |
| `InterestRate` | Decimal/Float | ✓ Required | >= 0 | Interest rate per period | No |
| `InterestType` | Text/String | ✓ Required | Must be one of: 'Simple', 'Compound' | Method to calculate interest on the loan | No |
| `PrincipalDeadline` | Integer | ✓ Required | >= 1 | Number of periods by which the principal must be repaid | No |
| `InterestRepaymentFrequency` | Integer | ✓ Required | >= 1 | Frequency (in periods) at which interest payments are made to the investor | No |
| `PrincipalRepaymentFrequency` | Integer | ✓ Required | >= 1 | Periods between each installment of principal repayment | No |
| `MinAmount` | Decimal/Float | ✓ Required | >= 0 | Minimum amount that can be borrowed from this investor via this loan | No |
| `MaxAmount` | Decimal/Float | ✓ Required | >= 0, MinAmount <= MaxAmount | Maximum amount that can be borrowed from this investor via this loan | No |
| `NumInstallments` | Integer | ✓ Required | >= 1 | Number of installments in which the principal is repaid | No |

---


---

### Example Queries

```sql
-- Basic table exploration
SELECT *
FROM input_investor_capital
LIMIT 10;

-- Row count and data coverage
SELECT COUNT(*) as row_count
FROM input_investor_capital
WHERE RunID = '{run_id}';
```

---

## input_investors

### Overview
**Type:** Input  
**Row Count Schema Fields:** 2

Master reference table mapping InvestorIDs to investor names and details.

---

### Grain
**Primary Key:** `InvestorID`

One row per unique investor

---

### Relationships
- No foreign key relationships defined in schema

---

### Business Context

Simple lookup table that associates investor identifiers with their names. Used in conjunction with Investor Capital and Investor Repayment Schedule tables to model debt financing from various capital sources.

**Update Cadence:** Updated when new investors are added to the portfolio

---

### Fields

| Field | Type | Required | Validation | Description | PII |
|------|------|----------|------------|-------------|-----|
| `InvestorID` | Text/String | ✓ Required | None | 🔑 PK | No |
| `InvestorName` | Text/String | ✓ Required | None | — | Possible |

---


---

### Example Queries

```sql
-- Basic table exploration
SELECT *
FROM input_investors
LIMIT 10;

-- Row count and data coverage
SELECT COUNT(*) as row_count
FROM input_investors;
```

---

## input_investor_repayment_schedule

### Overview
**Type:** Input  
**Row Count Schema Fields:** 4

Fixed schedule of interest and principal payments to investors by period.

---

### Grain
**Primary Key:** `RunID + InvestorCapitalID + PeriodID + PaymentType`

One row per RunID + InvestorCapitalID + PeriodID combination with a scheduled payment

---

### Relationships
- **InvestorCapitalID** → `[investor_capital.InvestorCapitalID]`
- **PeriodID** → `[time_periods.PeriodID]`

---

### Business Context

Translates the loan terms from input_investor_capital into period-by-period payment requirements. The model treats these as hard constraints on cash outflows. Interest payments typically occur periodically (monthly/quarterly) while principal payments occur at maturity.

**Update Cadence:** Generated from Investor Capital terms when loans are created

---

### Fields

| Field | Type | Required | Validation | Description | PII |
|------|------|----------|------------|-------------|-----|
| `RunID` | Text/String | ✓ Required | None | 🔑 PK | No |
| `InvestorCapitalID` | Text/String | ✓ Required | None | 🔑 PK 🔗 FK → [investor_capital.InvestorCapitalID] | No |
| `PeriodID` | Integer | ✓ Required | None | 🔑 PK 🔗 FK → [time_periods.PeriodID] | No |
| `PaymentType` | Text/String | ✓ Required | Must be one of: 'Interest', 'Principal' | 🔑 PK | No |
| `Amount` | Decimal/Float | ✓ Required | >= 0 | — | No |

---


---

### Example Queries

```sql
-- Basic table exploration
SELECT *
FROM input_investor_repayment_schedule
LIMIT 10;

-- Row count and data coverage
SELECT COUNT(*) as row_count
FROM input_investor_repayment_schedule
WHERE RunID = '{run_id}';

-- Temporal coverage check
SELECT 
    MIN(PeriodID) as earliest_period,
    MAX(PeriodID) as latest_period,
    COUNT(DISTINCT PeriodID) as period_count
FROM input_investor_repayment_schedule
WHERE RunID = '{run_id}';
```

---

## input_net_new_capacities

### Overview
**Type:** Input  
**Row Count Schema Fields:** 4

Incremental deployment capacity generated by marketing spend (cross-sectional COGS investment).

---

### Grain
**Primary Key:** `RunID + InvestorCapitalID + PeriodID`

One row per RunID + InvestorCapitalID + PeriodID

---

### Relationships
- **InvestorCapitalID** → `[investor_capital.InvestorCapitalID]`
- **PeriodID** → `[time_periods.PeriodID]`

---

### Business Context

Represents **capacity creation through marketing**. When COGS are invested in customer acquisition (e.g., direct mail campaigns), they generate new borrower capacity in future periods. This table models the lag and magnitude of that capacity generation, allowing the optimizer to trade off current marketing spend against future deployment opportunities.

**Update Cadence:** Based on historical campaign response analysis

---

### Fields

| Field | Type | Required | Validation | Description | PII |
|------|------|----------|------------|-------------|-----|
| `RunID` | Text/String | ✓ Required | None | 🔑 PK | No |
| `InvestorCapitalID` | Text/String | ✓ Required | None | 🔑 PK 🔗 FK → [investor_capital.InvestorCapitalID] | No |
| `PeriodID` | Integer | ✓ Required | None | 🔑 PK 🔗 FK → [time_periods.PeriodID] | No |
| `RollRate` | Decimal/Float | Optional | >= 0 and <= 1. Required if EnableNetNewConstraint is "Yes" | — | No |
| `NetNewCapacity` | Decimal/Float | Optional | >= 0. If EnableNetNewConstraint is "Yes", it's required for at least the first NetNewWindow periods for each InvestorCapitalID | — | No |

---


---

### Example Queries

```sql
-- Basic table exploration
SELECT *
FROM input_net_new_capacities
LIMIT 10;

-- Row count and data coverage
SELECT COUNT(*) as row_count
FROM input_net_new_capacities
WHERE RunID = '{run_id}';

-- Temporal coverage check
SELECT 
    MIN(PeriodID) as earliest_period,
    MAX(PeriodID) as latest_period,
    COUNT(DISTINCT PeriodID) as period_count
FROM input_net_new_capacities
WHERE RunID = '{run_id}';
```

---

## input_parameters

### Overview
**Type:** Input  
**Row Count Schema Fields:** 2

Defines the fundamental parameters for running the optimization simulation, including objective function, time boundaries, and initial conditions.

---

### Grain
**Primary Key:** `RunID`

One row per RunID (wide-format table: each parameter is a separate column)

---

### Relationships
- No foreign key relationships defined in schema

---

### Business Context

The Parameters table is the control panel for each optimization run. It defines:
- **Objective Function**: Either maximize ending bank balance or minimize the crossover point (first period where assets exceed liabilities)
- **Time Horizon**: Start and end periods for the simulation window
- **Initial Conditions**: Starting bank balance before any simulation decisions
- **Solver Settings**: MIPGap controls the Mixed Integer Programming solver's precision/speed tradeoff

**Update Cadence:** Created once per simulation scenario

---

### Fields

| Field | Type | Required | Validation | Description | PII |
|------|------|----------|------------|-------------|-----|
| `RunID` | Text/String | ✓ Required | None | 🔑 PK | No |
| `Name` | Text/String | ✓ Required | None | — | Possible |
| `Value` | Text/String | ✓ Required | None | — | No |

---

### Field Details

**StartBalance:**
- Initial bank balance at the beginning of StartPeriod
- **Sourced from**: `month_end_actuals.Balance` WHERE `PeriodLabel = [last day of prior month]` AND `PortfolioID = 'All'`
- Represents cash position before any optimization decisions
- Must match actual ending balance from previous month for accuracy
- Critical to cash flow feasibility constraints

**StartPeriod / EndPeriod:**
- Define the optimization window (first and last decision periods)
- Reference PeriodIDs from input_time_periods table
- Typically spans 12-60 months

**MIPGap:**
- Mixed Integer Programming solver tolerance setting
- Lower values = more precise but slower solve times
- Typical range: 0.001 (0.1%) to 0.05 (5%)

**Objective:**
- "MaximizeBankBalance": Maximize ending cash position
- "MinimizeCrossoverPoint": Minimize first period where assets > liabilities


---

### Example Queries

```sql
-- Basic table exploration
SELECT *
FROM input_parameters
LIMIT 10;

-- Row count and data coverage
SELECT COUNT(*) as row_count
FROM input_parameters
WHERE RunID = '{run_id}';
```

---

## input_performance_curves

### Overview
**Type:** Input  
**Row Count Schema Fields:** 9

Time-series performance projections showing expected returns, interest income, and charge-offs over the life of deployed capital.

---

### Grain
**Primary Key:** `RunID + CustomerGroupID + PeriodID + PeriodsSinceDeployment`

One row per RunID + CustomerGroupID + PeriodID + PeriodsSinceDeployment

---

### Relationships
- **CustomerGroupID** → `[customer_groups.CustomerGroupID]`
- **PeriodID** → `[time_periods.PeriodID]`

---

### Business Context

Performance curves define the **expected financial behavior** of deployed capital over time. The optimizer uses these to:
- **Forecast cash returns** from borrower repayments
- **Model interest income** realized from loan portfolios  
- **Provision for charge-offs** and credit losses
- **Differentiate performance** between first-time and repeat borrowers

**Key Fields:**
- **ReturnRate**: Repayment rate for new borrowers as % of deployment
- **RepeatReturnRate**: Repayment rate for returning customers (typically higher)
- **InterestPercentage**: Interest as % of deployment for new borrowers  
- **InterestPercentageRepeats**: Interest % for repeat borrowers
- **ChargeOffPercentage**: Credit losses as % of deployment
- **PeriodsSinceDeployment**: Loan age/vintage (0 = deployment period, 12 = 1 year old)

Curves are calibrated from historical vintage analysis and projected forward with adjustments for seasonality, portfolio maturation, and credit quality.

**Update Cadence:** Monthly or quarterly based on updated portfolio performance data

---

### Fields

| Field | Type | Required | Validation | Description | PII |
|------|------|----------|------------|-------------|-----|
| `RunID` | Text/String | ✓ Required | None | 🔑 PK | No |
| `CustomerGroupID` | Text/String | ✓ Required | None | 🔑 PK 🔗 FK → [customer_groups.CustomerGroupID] | No |
| `PeriodID` | Integer | ✓ Required | None | 🔑 PK 🔗 FK → [time_periods.PeriodID] | No |
| `PeriodsSinceDeployment` | Integer | ✓ Required | >= 0 | 🔑 PK | No |
| `ReturnRate` | Decimal/Float | ✓ Required | >= 0 | — | No |
| `RepeatReturnRate` | Decimal/Float | ✓ Required | >= 0 | — | No |
| `InterestPercentage` | Decimal/Float | ✓ Required | >= 0 and <= 1, InterestPercentage * ReturnRate >= ChargeOffPercentage | — | No |
| `InterestPercentageRepeats` | Decimal/Float | ✓ Required | >= 0 and <= 1, InterestPercentageRepeats * RepeatReturnRate >= ChargeOffPercentageRepeats | — | No |
| `ChargeOffPercentage` | Decimal/Float | ✓ Required | >= 0 and <= 1 | — | No |
| `ChargeOffPercentageRepeats` | Decimal/Float | ✓ Required | >= 0 and <= 1 | — | No |

---

### Field Details

**Critical Performance Metrics:**

**ReturnRate:**
- Percentage of deployed capital returned in a specific period for **new borrowers**
- Specified period = PeriodID + PeriodsSinceDeployment
- Example: If PeriodID=45 and PeriodsSinceDeployment=12, this shows return in period 57 from deployment in period 45

**RepeatReturnRate:**
- Same as ReturnRate but for **repeat/returning customers**
- Typically higher than new customer returns (better credit quality, proven payment history)
- Enables optimizer to value repeat customer cultivation

**InterestPercentage:**
- Interest income as % of deployment amount for **new customers**
- Multiply by (deployment × ReturnRate) to get dollar interest income
- Constraint: `InterestPercentage × ReturnRate >= ChargeOffPercentage` (interest must cover losses)

**InterestPercentageRepeats:**
- Interest % for **repeat customers**
- Usually higher than new customers due to better loan terms
- Same economic viability constraint applies

**ChargeOffPercentage / ChargeOffPercentageRepeats:**
- Expected credit losses as % of deployment
- Represents principal that will not be repaid
- Used for loss provisioning and profitability calculations

**PeriodsSinceDeployment:**
- Number of periods elapsed since capital was deployed (loan age/vintage)
- 0 = deployment period (no returns yet)
- Typically ranges from 0 to 24+ periods depending on loan term
- Defines the repayment curve shape over time

**Curve Calibration Notes:**
- Curves derived from historical vintage analysis
- Adjusted for seasonality (via PeriodID) and portfolio maturation
- Cumulative returns across all PeriodsSinceDeployment should not exceed 100% + total interest
- Validate economic viability: interest income must exceed charge-offs


---

### Example Queries

```sql
-- Basic table exploration
SELECT *
FROM input_performance_curves
LIMIT 10;

-- Row count and data coverage
SELECT COUNT(*) as row_count
FROM input_performance_curves
WHERE RunID = '{run_id}';

-- Temporal coverage check
SELECT 
    MIN(PeriodID) as earliest_period,
    MAX(PeriodID) as latest_period,
    COUNT(DISTINCT PeriodID) as period_count
FROM input_performance_curves
WHERE RunID = '{run_id}';

-- Customer group breakdown
SELECT 
    CustomerGroupID,
    COUNT(*) as record_count
FROM input_performance_curves
WHERE RunID = '{run_id}'
GROUP BY CustomerGroupID
ORDER BY record_count DESC;
```

---

## input_periods_config

### Overview
**Type:** Input  
**Row Count Schema Fields:** 5

Per-period configuration including balance floor, global deployment cap, and COGS seasonality adjustment.

---

### Grain
**Primary Key:** `RunID + PeriodID`

One row per RunID + PeriodID with special configuration

---

### Relationships
- **PeriodID** → `[time_periods.PeriodID]`

---

### Business Context

Defines per-period operational constraints for the optimizer: minimum bank balance floor, global deployment cap, and a COGS seasonality multiplier.

**Update Cadence:** Set once when defining simulation parameters; rarely changes

---

### Fields

| Field | Type | Required | Validation | Description | PII |
|------|------|----------|------------|-------------|-----|
| `RunID` | Text/String | ✓ Required | None | 🔑 PK | No |
| `PeriodID` | Integer | ✓ Required | None | 🔑 PK 🔗 FK → [time_periods.PeriodID] | No |
| `PeriodLabel` | Text/String | ✓ Required | None | Year-Month label (YYYY-MM) for the period | No |
| `BalanceLowerBound` | Decimal/Float | ✓ Required | None | Minimum acceptable bank balance at end of period | No |
| `DeploymentCapacity` | Decimal/Float | ✓ Required | >= 0 | Maximum capital that can be deployed (over all customer groups) in this period | No |
| `COGSAdjustFactor` | Decimal/Float | ✓ Required | None | Seasonality adjustment factor applied to COGS in this period (e.g., 100% = no adjustment) | No |

---


---

### Example Queries

```sql
-- Basic table exploration
SELECT *
FROM input_periods_config
LIMIT 10;

-- Row count and data coverage
SELECT COUNT(*) as row_count
FROM input_periods_config
WHERE RunID = '{run_id}';

-- Temporal coverage check
SELECT 
    MIN(PeriodID) as earliest_period,
    MAX(PeriodID) as latest_period,
    COUNT(DISTINCT PeriodID) as period_count
FROM input_periods_config
WHERE RunID = '{run_id}';
```

---

## input_portfolios

### Overview
**Type:** Input  
**Row Count Schema Fields:** 3

Defines portfolio groupings of customer groups for aggregated deployment constraints.

---

### Grain
**Primary Key:** `PortfolioID`

One row per Portfolio definition

---

### Relationships
- No foreign key relationships defined in schema

---

### Business Context

Portfolios allow imposing constraints across multiple customer groups (e.g., "Total Direct Mail deployments cannot exceed $X per period"). This enables strategic allocation decisions at a higher level than individual customer groups.

**Update Cadence:** Updated when portfolio strategy or structure changes

---

### Fields

| Field | Type | Required | Validation | Description | PII |
|------|------|----------|------------|-------------|-----|
| `PortfolioID` | Text/String | ✓ Required | None | 🔑 PK | No |
| `PortfolioLabel` | Text/String | ✓ Required | None | — | No |
| `Managed` | Text/String | ✓ Required | Must be one of: 'Yes', 'No' | — | No |

---


---

### Example Queries

```sql
-- Basic table exploration
SELECT *
FROM input_portfolios
LIMIT 10;

-- Row count and data coverage
SELECT COUNT(*) as row_count
FROM input_portfolios;
```

---

## input_portfolio_deployments

### Overview
**Type:** Input  
**Row Count Schema Fields:** 5

Defines deployment targets or limits at the portfolio level across a range of periods.

---

### Grain
**Primary Key:** `PortfolioID + FromPeriodID + ToPeriodID + ConstraintType`

One row per portfolio, period range, and constraint type.

---

### Relationships
- **PortfolioID** → `[portfolios.PortfolioID]`
- **FromPeriodID** → `[time_periods.PeriodID]`
- **ToPeriodID** → `[time_periods.PeriodID]`

---

### Business Context

Allows imposing constraints like "Portfolio X must deploy exactly $Y between periods A and B" (Equal) or "Portfolio X cannot exceed $Z in total deployments over a quarter" (LessThanOrEqual). Provides strategic control over portfolio-level deployment allocation, complementing the per-customer-group constraints in `input_customer_capacities`. Results against these constraints are reported in `output_portfolio_deployments_slacks`.

**Update Cadence:** Set based on portfolio-level deployment strategy and risk appetite

---

### Fields

| Field | Type | Required | Validation | Description | PII |
|------|------|----------|------------|-------------|-----|
| `PortfolioID` | Text/String | ✓ Required | None | 🔑 PK 🔗 FK → [portfolios.PortfolioID] | No |
| `FromPeriodID` | Integer | ✓ Required | FromPeriodID <= ToPeriodID | 🔑 PK 🔗 FK → [time_periods.PeriodID] | No |
| `ToPeriodID` | Integer | ✓ Required | None | 🔑 PK 🔗 FK → [time_periods.PeriodID] | No |
| `ConstraintType` | Text/String | ✓ Required | Must be one of "Equal" or "LessThanOrEqual". | 🔑 PK | No |
| `QuantityDeployed` | Decimal/Float | ✓ Required | >= 0 | — | No |

---


---

### Example Queries

```sql
-- Basic table exploration
SELECT *
FROM input_portfolio_deployments
LIMIT 10;

-- Row count and data coverage
SELECT COUNT(*) as row_count
FROM input_portfolio_deployments;
```

---

## input_portfolios_config

### Overview
**Type:** Input  
**Row Count Schema Fields:** 6

Maps customer groups to portfolios and sets portfolio-level constraints.

---

### Grain
**Primary Key:** `RunID + PortfolioID + PeriodID`

One row per RunID + PortfolioID + PeriodID

---

### Relationships
- **PortfolioID** → `[portfolios.PortfolioID]`
- **PeriodID** → `[time_periods.PeriodID]`

---

### Business Context

Links individual customer groups to their parent portfolios, enabling the optimizer to enforce portfolio-level constraints (minimum/maximum deployment targets, risk concentration limits).

**Update Cadence:** Updated when customer group assignments change

---

### Fields

| Field | Type | Required | Validation | Description | PII |
|------|------|----------|------------|-------------|-----|
| `RunID` | Text/String | ✓ Required | None | 🔑 PK | No |
| `PortfolioID` | Text/String | ✓ Required | None | 🔑 PK 🔗 FK → [portfolios.PortfolioID] | No |
| `PeriodID` | Integer | ✓ Required | None | 🔑 PK 🔗 FK → [time_periods.PeriodID] | No |
| `COGSAdjustFactor` | Decimal/Float | Optional | >= 0, required in [StartPeriod, EndPeriod] | — | No |
| `Overhead` | Decimal/Float | Optional | >= 0, required in [StartPeriod, EndPeriod] | — | No |
| `TribalFee` | Decimal/Float | Optional | >= 0, required in [StartPeriod, EndPeriod] | — | No |
| `TribalFeePercentage` | Decimal/Float | ✓ Required | >= 0 | — | No |

---


---

### Example Queries

```sql
-- Basic table exploration
SELECT *
FROM input_portfolios_config
LIMIT 10;

-- Row count and data coverage
SELECT COUNT(*) as row_count
FROM input_portfolios_config
WHERE RunID = '{run_id}';

-- Temporal coverage check
SELECT 
    MIN(PeriodID) as earliest_period,
    MAX(PeriodID) as latest_period,
    COUNT(DISTINCT PeriodID) as period_count
FROM input_portfolios_config
WHERE RunID = '{run_id}';
```

---

## input_relative_deployments

### Overview
**Type:** Input  
**Row Count Schema Fields:** 3

Defines relative deployment relationships or ratios between customer groups.

---

### Grain
**Primary Key:** `RunID + Year + Month`

One row per RunID + relationship constraint

---

### Relationships
- No foreign key relationships defined in schema

---

### Business Context

Enables strategic allocation policies expressed as ratios between segments. For example, maintaining a minimum percentage of deployments to repeat customers or limiting concentration in any single risk tier.

**Update Cadence:** Set based on strategic deployment mix policy

---

### Fields

| Field | Type | Required | Validation | Description | PII |
|------|------|----------|------------|-------------|-----|
| `RunID` | Text/String | ✓ Required | None | 🔑 PK | No |
| `Year` | Integer | ✓ Required | None | 🔑 PK | No |
| `Month` | Integer | ✓ Required | Must be between 1 and 12. | 🔑 PK | No |
| `RelativeWeight` | Decimal/Float | ✓ Required | >= 0 | — | No |

---


---

### Example Queries

```sql
-- Basic table exploration
SELECT *
FROM input_relative_deployments
LIMIT 10;

-- Row count and data coverage
SELECT COUNT(*) as row_count
FROM input_relative_deployments
WHERE RunID = '{run_id}';
```

---

## input_repeats_distribution

### Overview
**Type:** Input  
**Row Count Schema Fields:** 4

Distribution of repeat versus new customers within deployment volumes, by customer group and period.

---

### Grain
**Primary Key:** `RunID + CustomerGroupID + PeriodID + PeriodsSinceDeployment`

One row per RunID + CustomerGroupID + PeriodID

---

### Relationships
- **CustomerGroupID** → `[customer_groups.CustomerGroupID]`
- **PeriodID** → `[time_periods.PeriodID]`

---

### Business Context

Repeat customers typically have better performance (lower losses, higher retention) than new customers. This table tells the optimizer what percentage of deployments will be repeats so it can apply the appropriate performance curve (ReturnRate vs. RepeatReturnRate).

**Update Cadence:** Updated monthly/quarterly based on observed repeat behavior

---

### Fields

| Field | Type | Required | Validation | Description | PII |
|------|------|----------|------------|-------------|-----|
| `RunID` | Text/String | ✓ Required | None | 🔑 PK | No |
| `CustomerGroupID` | Text/String | ✓ Required | None | 🔑 PK 🔗 FK → [customer_groups.CustomerGroupID] | No |
| `PeriodID` | Integer | ✓ Required | None | 🔑 PK 🔗 FK → [time_periods.PeriodID] | No |
| `PeriodsSinceDeployment` | Integer | ✓ Required | >= 0 | 🔑 PK | No |
| `RepeatRate` | Decimal/Float | ✓ Required | >= 0 | — | No |

---


---

### Example Queries

```sql
-- Basic table exploration
SELECT *
FROM input_repeats_distribution
LIMIT 10;

-- Row count and data coverage
SELECT COUNT(*) as row_count
FROM input_repeats_distribution
WHERE RunID = '{run_id}';

-- Temporal coverage check
SELECT 
    MIN(PeriodID) as earliest_period,
    MAX(PeriodID) as latest_period,
    COUNT(DISTINCT PeriodID) as period_count
FROM input_repeats_distribution
WHERE RunID = '{run_id}';

-- Customer group breakdown
SELECT 
    CustomerGroupID,
    COUNT(*) as record_count
FROM input_repeats_distribution
WHERE RunID = '{run_id}'
GROUP BY CustomerGroupID
ORDER BY record_count DESC;
```

---

## input_time_periods

### Overview
**Type:** Input  
**Row Count Schema Fields:** 2

Maps PeriodID identifiers used throughout the simulation to actual calendar weeks (YYYY-MM-DD, Monday start).

---

### Grain
**Primary Key:** `RunID + PeriodID`

One row per RunID + monthly time period in the simulation horizon

---

### Relationships
- No foreign key relationships defined in schema

---

### Business Context

Essential reference table that translates numeric PeriodIDs to human-readable weekly dates. All other tables reference periods by PeriodID, making this the temporal foundation of the model. The optimizer generates a continuous sequence of weekly periods from the earliest data point through the simulation end date.

**Update Cadence:** Generated automatically based on StartPeriod and EndPeriod from Parameters table

---

### Fields

| Field | Type | Required | Validation | Description | PII |
|------|------|----------|------------|-------------|-----|
| `RunID` | Text/String | ✓ Required | None | 🔑 PK | No |
| `PeriodID` | Integer | ✓ Required | None | 🔑 PK | No |
| `PeriodLabel` | Text/String | ✓ Required | YYYY-MM-DD format (e.g. '2024-07-01'). Must be a Monday. Must be parsable to datetime. | — | No |

---

### Field Details

**PeriodID:**
- Numeric identifier for consistent time period referencing
- Maps to actual calendar weeks via PeriodLabel
- Used as foreign key across all temporal tables

**PeriodLabel:**
- The **Monday date** of that week in YYYY-MM-DD format
- Represents the start of a weekly simulation period
- Generated automatically from earliest_period through simulation_end

**Generation Logic:**
- Period 1 = 2017-07-03 (first Monday of July 2017)
- Sequential weekly periods (every Monday) through simulation end
- Continuous sequence generated through simulation end period
- StartPeriod and EndPeriod from Parameters table define optimization window

**Lookup pattern (floor to containing week):**
```sql
SELECT PeriodID FROM input_time_periods
WHERE RunID = '{run_id}' AND PeriodLabel <= 'YYYY-MM-DD'
ORDER BY PeriodLabel DESC
LIMIT 1
```


---

### Example Queries

```sql
-- Basic table exploration
SELECT *
FROM input_time_periods
LIMIT 10;

-- Row count and data coverage
SELECT COUNT(*) as row_count
FROM input_time_periods
WHERE RunID = '{run_id}';

-- Temporal coverage check
SELECT 
    MIN(PeriodID) as earliest_period,
    MAX(PeriodID) as latest_period,
    COUNT(DISTINCT PeriodID) as period_count
FROM input_time_periods
WHERE RunID = '{run_id}';
```

---

## output_aggregated_deployments_slacks

### Overview
**Type:** Output  
**Row Count Schema Fields:** 5

Reports how much unused capacity remains against aggregated deployment constraints after optimization.

---

### Grain
**Primary Key:** `RunID + FromPeriodID + ToPeriodID`

One row per RunID + aggregated deployment constraint defined in `input_aggregated_deployments`.

---

### Relationships
- **FromPeriodID** → `[time_periods.PeriodID]`
- **ToPeriodID** → `[time_periods.PeriodID]`

---

### Business Context

For each aggregated deployment constraint from `input_aggregated_deployments`, shows the input capacity cap (`InputAggDeploymentCapacity`), the unused portion (`AggDeploymentCapacitySlack`), and the amount actually utilized (`AggDeploymentCapacityUtilized`). A slack of 0 means the constraint was binding; a positive slack means the optimizer had room to deploy more but was limited by other factors such as cash or customer-level capacity.

**Update Cadence:** Generated fresh with each optimization run

---

### Fields

| Field | Type | Required | Validation | Description | PII |
|------|------|----------|------------|-------------|-----|
| `RunID` | Text/String | ✓ Required | None | 🔑 PK | No |
| `FromPeriodID` | Integer | ✓ Required | None | 🔑 PK 🔗 FK → [time_periods.PeriodID] | No |
| `ToPeriodID` | Integer | ✓ Required | None | 🔑 PK 🔗 FK → [time_periods.PeriodID] | No |
| `InputAggDeploymentCapacity` | Decimal/Float | ✓ Required | >= 0 | — | No |
| `AggDeploymentCapacitySlack` | Decimal/Float | ✓ Required | >= 0 | — | No |
| `AggDeploymentCapacityUtilized` | Decimal/Float | ✓ Required | >= 0 | — | No |

---


---

### Example Queries

```sql
-- Basic table exploration
SELECT *
FROM output_aggregated_deployments_slacks
LIMIT 10;

-- Row count and data coverage
SELECT COUNT(*) as row_count
FROM output_aggregated_deployments_slacks
WHERE RunID = '{run_id}';
```

---

## output_customer_deployments_slacks

### Overview
**Type:** Output  
**Row Count Schema Fields:** 5

Reports unused deployment capacity per customer group and period after optimization.

---

### Grain
**Primary Key:** `RunID + CustomerGroupID + PeriodID`

One row per RunID + customer group and period.

---

### Relationships
- **CustomerGroupID** → `[customer_groups.CustomerGroupID]`
- **PeriodID** → `[time_periods.PeriodID]`

---

### Business Context

For each per-group capacity constraint from `input_customer_capacities`, shows how much capacity was utilized vs. remaining. Helps identify which customer segments are capacity-constrained (slack near zero) vs. cash-constrained or return-limited (high slack) in the optimal solution. A segment with consistently high slack may indicate over-estimated demand forecasts.

**Update Cadence:** Generated fresh with each optimization run

---

### Fields

| Field | Type | Required | Validation | Description | PII |
|------|------|----------|------------|-------------|-----|
| `RunID` | Text/String | ✓ Required | None | 🔑 PK | No |
| `CustomerGroupID` | Text/String | ✓ Required | None | 🔑 PK 🔗 FK → [customer_groups.CustomerGroupID] | No |
| `PeriodID` | Integer | ✓ Required | None | 🔑 PK 🔗 FK → [time_periods.PeriodID] | No |
| `InputDeploymentCapacity` | Decimal/Float | ✓ Required | >= 0 | — | No |
| `DeploymentCapacitySlack` | Decimal/Float | ✓ Required | >= 0 | — | No |
| `DeploymentCapacityUtilized` | Decimal/Float | ✓ Required | >= 0 | — | No |

---


---

### Example Queries

```sql
-- Basic table exploration
SELECT *
FROM output_customer_deployments_slacks
LIMIT 10;

-- Row count and data coverage
SELECT COUNT(*) as row_count
FROM output_customer_deployments_slacks
WHERE RunID = '{run_id}';

-- Temporal coverage check
SELECT 
    MIN(PeriodID) as earliest_period,
    MAX(PeriodID) as latest_period,
    COUNT(DISTINCT PeriodID) as period_count
FROM output_customer_deployments_slacks
WHERE RunID = '{run_id}';

-- Customer group breakdown
SELECT 
    CustomerGroupID,
    COUNT(*) as record_count
FROM output_customer_deployments_slacks
WHERE RunID = '{run_id}'
GROUP BY CustomerGroupID
ORDER BY record_count DESC;
```

---

## output_deployments_slacks

### Overview
**Type:** Output  
**Row Count Schema Fields:** 4

Reports unused global deployment capacity per period after optimization.

---

### Grain
**Primary Key:** `RunID + PeriodID`

One row per RunID + period.

---

### Relationships
- **PeriodID** → `[time_periods.PeriodID]`

---

### Business Context

Shows how much of the global period-level deployment cap (from `input_periods_config.DeploymentCapacity`) was actually used in each period. A high slack indicates the global cap is not the binding constraint in that period; a zero slack means the global capacity limited total deployments. Use alongside `output_customer_deployments_slacks` to distinguish global vs. per-group bottlenecks.

**Update Cadence:** Generated fresh with each optimization run

---

### Fields

| Field | Type | Required | Validation | Description | PII |
|------|------|----------|------------|-------------|-----|
| `RunID` | Text/String | ✓ Required | None | 🔑 PK | No |
| `PeriodID` | Integer | ✓ Required | None | 🔑 PK 🔗 FK → [time_periods.PeriodID] | No |
| `InputDeploymentCapacity` | Decimal/Float | ✓ Required | >= 0 | — | No |
| `DeploymentCapacitySlack` | Decimal/Float | ✓ Required | >= 0 | — | No |
| `DeploymentCapacityUtilized` | Decimal/Float | ✓ Required | >= 0 | — | No |

---


---

### Example Queries

```sql
-- Basic table exploration
SELECT *
FROM output_deployments_slacks
LIMIT 10;

-- Row count and data coverage
SELECT COUNT(*) as row_count
FROM output_deployments_slacks
WHERE RunID = '{run_id}';

-- Temporal coverage check
SELECT 
    MIN(PeriodID) as earliest_period,
    MAX(PeriodID) as latest_period,
    COUNT(DISTINCT PeriodID) as period_count
FROM output_deployments_slacks
WHERE RunID = '{run_id}';
```

---

## output_portfolio_deployments_slacks

### Overview
**Type:** Output  
**Row Count Schema Fields:** 7

Reports unused capacity against portfolio-level deployment constraints after optimization.

---

### Grain
**Primary Key:** `RunID + PortfolioID + FromPeriodID + ToPeriodID + ConstraintType`

One row per RunID + portfolio deployment constraint defined in `input_portfolio_deployments`.

---

### Relationships
- **PortfolioID** → `[portfolios.PortfolioID]`
- **FromPeriodID** → `[time_periods.PeriodID]`
- **ToPeriodID** → `[time_periods.PeriodID]`

---

### Business Context

For each portfolio deployment constraint from `input_portfolio_deployments`, shows the input target (`InputQuantityDeployed`), the unused portion (`QuantityDeployedSlack`), and the amount actually deployed (`QuantityDeployedUtilized`). For Equal constraints, slack of 0 confirms the optimizer met the exact target. For LessThanOrEqual constraints, positive slack means the portfolio deployed less than the ceiling.

**Update Cadence:** Generated fresh with each optimization run

---

### Fields

| Field | Type | Required | Validation | Description | PII |
|------|------|----------|------------|-------------|-----|
| `RunID` | Text/String | ✓ Required | None | 🔑 PK | No |
| `PortfolioID` | Text/String | ✓ Required | None | 🔑 PK 🔗 FK → [portfolios.PortfolioID] | No |
| `FromPeriodID` | Integer | ✓ Required | FromPeriodID <= ToPeriodID | 🔑 PK 🔗 FK → [time_periods.PeriodID] | No |
| `ToPeriodID` | Integer | ✓ Required | None | 🔑 PK 🔗 FK → [time_periods.PeriodID] | No |
| `ConstraintType` | Text/String | ✓ Required | Must be one of "Equal" or "LessThanOrEqual". | 🔑 PK | No |
| `InputQuantityDeployed` | Decimal/Float | ✓ Required | >= 0 | — | No |
| `QuantityDeployedSlack` | Decimal/Float | ✓ Required | None | — | No |
| `QuantityDeployedUtilized` | Decimal/Float | ✓ Required | >= 0 | — | No |

---


---

### Example Queries

```sql
-- Basic table exploration
SELECT *
FROM output_portfolio_deployments_slacks
LIMIT 10;

-- Row count and data coverage
SELECT COUNT(*) as row_count
FROM output_portfolio_deployments_slacks
WHERE RunID = '{run_id}';
```

---

## output_kpis

### Overview
**Type:** Output  
**Row Count Schema Fields:** 2

Key Performance Indicators calculated from the optimized solution.

---

### Grain
**Primary Key:** `RunID + Name`

One row per RunID + KPI metric (may be single-period or aggregated)

---

### Relationships
- No foreign key relationships defined in schema

---

### Business Context

Strategic metrics including:
- **Crossover Point**: First period where assets exceed liabilities
- **Total Capital Raised**: Cumulative fundraising across simulation
- **Total Deployments**: Cumulative lending volume
- **Net Interest Margin**: Spread between borrower interest and investor cost
- **Ending Bank Balance**: Final cash position
- **ROIC**: Return on invested capital
- **Vintage Returns**: Performance by deployment cohort

Used for scenario comparison and business case evaluation.

**Update Cadence:** To be determined

---

### Fields

| Field | Type | Required | Validation | Description | PII |
|------|------|----------|------------|-------------|-----|
| `RunID` | Text/String | ✓ Required | None | 🔑 PK | No |
| `Name` | Text/String | ✓ Required | None | 🔑 PK | Possible |
| `Value` | Text/String | ✓ Required | None | — | No |

---


---

### Example Queries

```sql
-- Basic table exploration
SELECT *
FROM output_kpis
LIMIT 10;

-- Row count and data coverage
SELECT COUNT(*) as row_count
FROM output_kpis
WHERE RunID = '{run_id}';
```

---

## output_ledger

### Overview
**Type:** Output  
**Row Count Schema Fields:** 22

Complete cash flow waterfall showing all inflows and outflows by period, culminating in ending bank balance.

---

### Grain
**Primary Key:** `RunID + EntryID`

One row per RunID + ledger transaction (EntryID); multiple entries exist per period

---

### Relationships
- **PeriodID** → `[time_periods.PeriodID]`
- **ReferencePeriodID** → `[time_periods.PeriodID]`
- **CogsID** → `[cogs.CogsID]`
- **InvestorID** → `[investors.InvestorID]`
- **CogsLabel** → `[cogs.CogsLabel]`
- **CogsType** → `[cogs.CogsType]`
- **InvestorName** → `[investors.InvestorName]`
- **InvestorCapitalID** → `[investor_capital.InvestorCapitalID]`
- **InvestorCapitalName** → `[investor_capital.InvestorCapitalName]`
- **CustomerGroupID** → `[customer_groups.CustomerGroupID]`
- **CustomerGroupName** → `[customer_groups.CustomerGroupName]`
- **CustomerGroupType** → `[customer_groups.CustomerGroupType]`
- **PortfolioID** → `[portfolios.PortfolioID]`

---

### Business Context

The comprehensive financial output showing:

**Inflows:**
- Starting balance
- Capital raised from investors
- Customer repayments (principal + interest)

**Outflows:**  
- Deployments to customers
- COGS (deployment costs and marketing)
- Investor repayments (interest + principal)
- Overhead expenses

**Result:**
- Ending bank balance (optimization objective if maximizing)
- Cumulative cash flow
- Period-by-period financial position

**Update Cadence:** To be determined

---

### Fields

| Field | Type | Required | Validation | Description | PII |
|------|------|----------|------------|-------------|-----|
| `RunID` | Text/String | ✓ Required | None | 🔑 PK | No |
| `EntryID` | Integer | ✓ Required | None | 🔑 PK | No |
| `PeriodID` | Integer | ✓ Required | None | 🔗 FK → [time_periods.PeriodID] | No |
| `EntryType` | Text/String | ✓ Required | Must be one of: 'Initial Balance', 'Raise', 'Deploy', 'Deploy to Repeats', 'Return', 'Interest Payment', 'Principal Payment', 'Scheduled Interest Payment', 'Scheduled Principal Payment', 'COGS', 'Direct Mail COGS Campaign', 'Overhead', 'TribalFee', 'BalanceSlack' | — | No |
| `Amount` | Decimal/Float | ✓ Required | None | — | No |
| `Balance` | Decimal/Float | Optional | None | — | No |
| `ReferencePeriodID` | Integer | Optional | None | 🔗 FK → [time_periods.PeriodID] | No |
| `CogsID` | Text/String | Optional | None | 🔗 FK → [cogs.CogsID] | No |
| `InvestorID` | Text/String | Optional | None | 🔗 FK → [investors.InvestorID] | No |
| `InterestReturn` | Decimal/Float | Optional | >= 0 | — | No |
| `PrincipalReturn` | Decimal/Float | Optional | >= 0 | — | No |
| `ChargeOff` | Decimal/Float | Optional | >= 0 | — | No |
| `Roll` | Decimal/Float | Optional | >= 0 | — | No |
| `NetNew` | Decimal/Float | Optional | >= 0 | — | No |
| `CogsLabel` | Text/String | Optional | None | 🔗 FK → [cogs.CogsLabel] | No |
| `CogsType` | Text/String | Optional | None | 🔗 FK → [cogs.CogsType] | No |
| `InvestorName` | Text/String | Optional | None | 🔗 FK → [investors.InvestorName] | Possible |
| `InvestorCapitalID` | Text/String | Optional | None | 🔗 FK → [investor_capital.InvestorCapitalID] | No |
| `InvestorCapitalName` | Text/String | Optional | None | 🔗 FK → [investor_capital.InvestorCapitalName] | Possible |
| `CustomerGroupID` | Text/String | Optional | None | 🔗 FK → [customer_groups.CustomerGroupID] | No |
| `CustomerGroupName` | Text/String | Optional | None | 🔗 FK → [customer_groups.CustomerGroupName] | Possible |
| `CustomerGroupType` | Text/String | Optional | None | 🔗 FK → [customer_groups.CustomerGroupType] | No |
| `PortfolioID` | Text/String | Optional | None | 🔗 FK → [portfolios.PortfolioID] | No |

---

### Field Details

**Cash Flow Waterfall Structure:**

**Starting Position:**
- Beginning bank balance (from prior period ending balance or StartBalance)

**Inflows (+):**
- **CapitalRaised**: Debt financing from investors
- **CustomerRepaymentsPrincipal**: Borrower principal repayments
- **CustomerRepaymentsInterest**: Interest income from borrowers

**Outflows (-):**
- **DeploymentsNew**: Capital deployed to new borrowers
- **DeploymentsRepeat**: Capital deployed to repeat borrowers
- **TotalCOGS**: All cost of goods sold (longitudinal + cross-sectional)
- **InvestorPaymentsInterest**: Interest paid to debt holders
- **InvestorPaymentsPrincipal**: Principal repaid to investors
- **Overhead**: Fixed operational expenses

**Ending Position:**
- **EndingBankBalance** = Starting + Inflows - Outflows
- This becomes next period's starting balance
- **Objective function target** if maximizing bank balance

**Key Metrics:**
- **CumulativeCashFlow**: Running total of net cash flow
- **CumulativeDeployments**: Total lending volume to date
- **CumulativeRaises**: Total capital raised to date


---

### Example Queries

```sql
-- Basic table exploration
SELECT *
FROM output_ledger
LIMIT 10;

-- Row count and data coverage
SELECT COUNT(*) as row_count
FROM output_ledger
WHERE RunID = '{run_id}';

-- Temporal coverage check
SELECT 
    MIN(PeriodID) as earliest_period,
    MAX(PeriodID) as latest_period,
    COUNT(DISTINCT PeriodID) as period_count
FROM output_ledger
WHERE RunID = '{run_id}';

-- Customer group breakdown
SELECT 
    CustomerGroupID,
    COUNT(*) as record_count
FROM output_ledger
WHERE RunID = '{run_id}'
GROUP BY CustomerGroupID
ORDER BY record_count DESC;
```

---

## output_ledger_pivot

### Overview
**Type:** Output  
**Row Count Schema Fields:** 20

Pivoted/transposed view of the ledger for easier period-over-period comparison.

---

### Grain
**Primary Key:** `RunID + PeriodID`

One row per RunID + period, with all financial flows aggregated as columns

---

### Relationships
- **PeriodID** → `[time_periods.PeriodID]`
- **PeriodLabel** → `[time_periods.PeriodLabel]`

---

### Business Context

Same data as output_ledger but arranged for horizontal time series analysis. Useful for visualizing trends and creating financial dashboards.

**Update Cadence:** To be determined

---

### Fields

| Field | Type | Required | Validation | Description | PII |
|------|------|----------|------------|-------------|-----|
| `RunID` | Text/String | ✓ Required | None | 🔑 PK | No |
| `PeriodID` | Integer | ✓ Required | None | 🔑 PK 🔗 FK → [time_periods.PeriodID] | No |
| `PeriodLabel` | Text/String | ✓ Required | None | 🔗 FK → [time_periods.PeriodLabel] | No |
| `TotalResult` | Decimal/Float | Optional | None | — | No |
| `FinalBalance` | Decimal/Float | Optional | None | — | No |
| `Surplus` | Decimal/Float | Optional | None | — | No |
| `BalanceSlack` | Decimal/Float | Optional | None | — | No |
| `COGS` | Decimal/Float | Optional | None | — | No |
| `Deploy` | Decimal/Float | Optional | None | — | No |
| `DeployToRepeats` | Decimal/Float | Optional | None | — | No |
| `DirectMailCOGSCampaign` | Decimal/Float | Optional | None | — | No |
| `InterestPayment` | Decimal/Float | Optional | None | — | No |
| `Overhead` | Decimal/Float | Optional | None | — | No |
| `PrincipalPayment` | Decimal/Float | Optional | None | — | No |
| `Raise` | Decimal/Float | Optional | None | — | No |
| `Return` | Decimal/Float | Optional | None | — | No |
| `ScheduledInterestPayment` | Decimal/Float | Optional | None | — | No |
| `ScheduledPrincipalPayment` | Decimal/Float | Optional | None | — | No |
| `TribalFee` | Decimal/Float | Optional | None | — | No |
| `Receivables` | Decimal/Float | Optional | None | — | No |
| `Liabilities` | Decimal/Float | Optional | None | — | No |

---


---

### Example Queries

```sql
-- Basic table exploration
SELECT *
FROM output_ledger_pivot
LIMIT 10;

-- Row count and data coverage
SELECT COUNT(*) as row_count
FROM output_ledger_pivot
WHERE RunID = '{run_id}';

-- Temporal coverage check
SELECT 
    MIN(PeriodID) as earliest_period,
    MAX(PeriodID) as latest_period,
    COUNT(DISTINCT PeriodID) as period_count
FROM output_ledger_pivot
WHERE RunID = '{run_id}';
```

---

## output_balances

### Overview
**Type:** Output  
**Row Count Schema Fields:** 2

Period-by-period ending bank balance from the optimized solution.

---

### Grain
**Primary Key:** `RunID + PeriodID`

One row per RunID + period.

---

### Relationships
- No foreign key relationships defined in schema

---

### Business Context

Tracks the bank balance at the end of each period throughout the simulation. Derived from the cumulative cash flows recorded in `output_ledger`. This is the key time-series view of financial health — the ending balance of the final period is the optimization objective when using the Maximize Bank Balance objective function. Use alongside `output_balances_slacks` to see how much headroom exists above the minimum balance floor each period.

**Update Cadence:** Generated fresh with each optimization run

---

### Fields

| Field | Type | Required | Validation | Description | PII |
|------|------|----------|------------|-------------|-----|
| `RunID` | Text/String | ✓ Required | None | 🔑 PK | No |
| `PeriodID` | Integer | ✓ Required | None | 🔑 PK | No |
| `Balance` | Decimal/Float | ✓ Required | None | — | No |

---


---

### Example Queries

```sql
-- Basic table exploration
SELECT *
FROM output_balances
LIMIT 10;

-- Row count and data coverage
SELECT COUNT(*) as row_count
FROM output_balances
WHERE RunID = '{run_id}';

-- Temporal coverage check
SELECT 
    MIN(PeriodID) as earliest_period,
    MAX(PeriodID) as latest_period,
    COUNT(DISTINCT PeriodID) as period_count
FROM output_balances
WHERE RunID = '{run_id}';
```

---

## output_financial

### Overview
**Type:** Output  
**Row Count Schema Fields:** 16

Annual rollup of all financial flows from the optimized solution.

---

### Grain
**Primary Key:** `RunID + Year`

One row per RunID + calendar year (>= 2020).

---

### Relationships
- No foreign key relationships defined in schema

---

### Business Context

Aggregates the period-level ledger entries from `output_ledger_pivot` to a yearly view, summing all cash inflows, outflows, and ending balances by calendar year. Useful for annual reporting, budget comparison, and high-level scenario analysis across multi-year simulation horizons. Mirrors the same financial line items as `output_ledger_pivot` but at annual granularity.

**Update Cadence:** Generated fresh with each optimization run

---

### Fields

| Field | Type | Required | Validation | Description | PII |
|------|------|----------|------------|-------------|-----|
| `RunID` | Text/String | ✓ Required | None | 🔑 PK | No |
| `Year` | Integer | ✓ Required | >=2020 | 🔑 PK | No |
| `BalanceSlack` | Decimal/Float | Optional | None | — | No |
| `COGS` | Decimal/Float | Optional | None | — | No |
| `Deploy` | Decimal/Float | Optional | None | — | No |
| `DeployToRepeats` | Decimal/Float | Optional | None | — | No |
| `DirectMailCOGSCampaign` | Decimal/Float | Optional | None | — | No |
| `InterestPayment` | Decimal/Float | Optional | None | — | No |
| `Overhead` | Decimal/Float | Optional | None | — | No |
| `PrincipalPayment` | Decimal/Float | Optional | None | — | No |
| `Raise` | Decimal/Float | Optional | None | — | No |
| `Return` | Decimal/Float | Optional | None | — | No |
| `ScheduledInterestPayment` | Decimal/Float | Optional | None | — | No |
| `ScheduledPrincipalPayment` | Decimal/Float | Optional | None | — | No |
| `TribalFee` | Decimal/Float | Optional | None | — | No |
| `TotalResult` | Decimal/Float | Optional | None | — | No |
| `FinalBalance` | Decimal/Float | Optional | None | — | No |

---


---

### Example Queries

```sql
-- Basic table exploration
SELECT *
FROM output_financial
LIMIT 10;

-- Row count and data coverage
SELECT COUNT(*) as row_count
FROM output_financial
WHERE RunID = '{run_id}';
```

---

## output_raises_slacks

### Overview
**Type:** Output  
**Row Count Schema Fields:** 5

Reports unused fundraising capacity per investor capital source and period after optimization.

---

### Grain
**Primary Key:** `RunID + InvestorCapitalID + PeriodID`

One row per RunID + investor capital source and period.

---

### Relationships
- **InvestorCapitalID** → `[investor_capital.InvestorCapitalID]`

---

### Business Context

For each investor capital source with a `MaxAmount` constraint (from `input_investor_capital`), shows how much of the allowable raise was actually used (`MaxAmountUtilized`) vs. left unused (`RaiseSlack`). A positive `RaiseSlack` means the optimizer chose not to raise the maximum available from that source — additional capital was either not needed or would have resulted in unnecessary interest obligations relative to the returns available.

**Update Cadence:** Generated fresh with each optimization run

---

### Fields

| Field | Type | Required | Validation | Description | PII |
|------|------|----------|------------|-------------|-----|
| `RunID` | Text/String | ✓ Required | None | 🔑 PK | No |
| `InvestorCapitalID` | Text/String | ✓ Required | None | 🔑 PK 🔗 FK → [investor_capital.InvestorCapitalID] | No |
| `PeriodID` | Integer | ✓ Required | None | 🔑 PK | No |
| `InputMaxAmount` | Decimal/Float | ✓ Required | >= 0 | — | No |
| `RaiseSlack` | Decimal/Float | ✓ Required | >= 0 | — | No |
| `MaxAmountUtilized` | Decimal/Float | ✓ Required | >= 0 | — | No |

---


---

### Example Queries

```sql
-- Basic table exploration
SELECT *
FROM output_raises_slacks
LIMIT 10;

-- Row count and data coverage
SELECT COUNT(*) as row_count
FROM output_raises_slacks
WHERE RunID = '{run_id}';

-- Temporal coverage check
SELECT 
    MIN(PeriodID) as earliest_period,
    MAX(PeriodID) as latest_period,
    COUNT(DISTINCT PeriodID) as period_count
FROM output_raises_slacks
WHERE RunID = '{run_id}';
```

---

## output_balances_slacks

### Overview
**Type:** Output  
**Row Count Schema Fields:** 5

Reports how much headroom the bank balance had above the minimum balance floor in each period.

---

### Grain
**Primary Key:** `RunID + PeriodID`

One row per RunID + period.

---

### Relationships
- No foreign key relationships defined in schema

---

### Business Context

For each period with a `BalanceLowerBound` constraint (from `input_periods_config`), shows the input floor (`InputBalanceLowerBound`), the distance between actual balance and that floor (`BalanceLowerBoundSlack`), and the utilized portion (`BalanceLowerBoundUtilized`). `BalanceSlack` measures any artificial infeasibility slack introduced when the model cannot meet the floor and must relax the constraint to remain feasible — a non-zero `BalanceSlack` signals a cash shortfall in that period.

**Update Cadence:** Generated fresh with each optimization run

---

### Fields

| Field | Type | Required | Validation | Description | PII |
|------|------|----------|------------|-------------|-----|
| `RunID` | Text/String | ✓ Required | None | 🔑 PK | No |
| `PeriodID` | Integer | ✓ Required | None | 🔑 PK | No |
| `InputBalanceLowerBound` | Decimal/Float | ✓ Required | None | — | No |
| `BalanceLowerBoundSlack` | Decimal/Float | ✓ Required | >=  0 | — | No |
| `BalanceLowerBoundUtilized` | Decimal/Float | ✓ Required | None | — | No |
| `BalanceSlack` | Decimal/Float | ✓ Required | >= 0 | — | No |

---


---

### Example Queries

```sql
-- Basic table exploration
SELECT *
FROM output_balances_slacks
LIMIT 10;

-- Row count and data coverage
SELECT COUNT(*) as row_count
FROM output_balances_slacks
WHERE RunID = '{run_id}';

-- Temporal coverage check
SELECT 
    MIN(PeriodID) as earliest_period,
    MAX(PeriodID) as latest_period,
    COUNT(DISTINCT PeriodID) as period_count
FROM output_balances_slacks
WHERE RunID = '{run_id}';
```

---


# Appendix

## Model Workflow Overview

1. **Parameter Setup**: Define objectives, time horizon, starting balance
2. **Input Data Preparation**:
   - Customer groups and segmentation
   - Performance curves (historical vintage data)
   - COGS structure (costs per segment)
   - Deployment capacities (demand constraints)
   - Investor capital terms (debt structure)
3. **Optimization Execution**: MIP solver determines optimal decisions
4. **Output Generation**:
   - Deployment schedule (how much to lend, to whom, when)
   - Fundraising schedule (how much to raise, from whom, when)
   - Financial projections (ledger, KPIs, cash flows)
5. **Scenario Analysis**: Compare multiple optimization runs with different assumptions

---

## Key Business Concepts

**Crossover Point:**
- First period where total assets exceed total liabilities
- Important for achieving self-sustainability
- Alternative objective to maximizing bank balance

**Vintage Returns:**
- Performance cohort analysis by deployment period
- Tracks repayment behavior over loan lifetime
- Used to calibrate performance curves

**Repeat Customer Value:**
- Returning borrowers typically have:
  - Higher approval rates (proven credit)
  - Better performance (lower charge-offs)
  - Lower acquisition costs (no new marketing spend)
- Separate performance curves model this difference

**Capacity Constraints:**
- Real-world demand limits prevent infinite deployment
- Represent saturation of qualified borrower pipeline
- Marketing investments can expand future capacity

**COGS Economics:**
- Longitudinal COGS scale with deployments (variable)
- Cross-sectional COGS are period-fixed (marketing, underwriting)
- Marketing spend creates future capacity (investment vs. expense trade-off)

---

## Data Quality Checks

### Critical Validations

1. **Performance Curve Economic Viability**:
```sql
-- Verify interest covers charge-offs
SELECT *
FROM input_performance_curves
WHERE RunID = '{run_id}'
  AND ((InterestPercentage * ReturnRate) < ChargeOffPercentage
   OR (InterestPercentageRepeats * RepeatReturnRate) < ChargeOffPercentageRepeats);
```

2. **Investor Repayment Schedule Completeness**:
```sql
-- Ensure all investor capital has repayment schedules
SELECT ic.InvestorCapitalID
FROM input_investor_capital ic
LEFT JOIN input_investor_repayment_schedule irs 
    ON ic.RunID = irs.RunID
    AND ic.InvestorCapitalID = irs.InvestorCapitalID
WHERE ic.RunID = '{run_id}'
  AND irs.InvestorCapitalID IS NULL;
```

3. **Capacity vs. Fix Deployment Consistency**:
```sql
-- Fixed deployments should not exceed capacities
-- Note: input_fix_deployments has no RunID; filter input_customer_capacities by RunID
SELECT 
    fd.CustomerGroupID,
    fd.PeriodID,
    fd.Quantity,
    cc.DeploymentCapacity
FROM input_fix_deployments fd
JOIN input_customer_capacities cc 
    ON fd.CustomerGroupID = cc.CustomerGroupID 
    AND fd.PeriodID = cc.PeriodID
    AND cc.RunID = '{run_id}'
WHERE fd.Quantity > cc.DeploymentCapacity;
```

4. **Time Period Continuity**:
```sql
-- Check for gaps in period sequence
WITH period_seq AS (
    SELECT 
        PeriodID,
        LAG(PeriodID) OVER (ORDER BY PeriodID) as prev_period
    FROM input_time_periods
    WHERE RunID = '{run_id}'
)
SELECT *
FROM period_seq
WHERE PeriodID - prev_period > 1;
```

---

## Change Log

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-01-20 | Generated | Initial comprehensive documentation with PDF context |

---

**Document End**
