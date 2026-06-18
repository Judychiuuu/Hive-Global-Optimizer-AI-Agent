# DE_NB_Apply_Scenario — Tool Notebook Spec

## Purpose
Receives a batch of SQL mutation strings, substitutes the `{run_id}` placeholder with the
actual RunID, and executes each statement via `spark.sql()`.

This notebook is called by `DE_NB_Main` after `DE_NB_CopyRun` has created the new run's
data. It applies the scenario changes (e.g. updated COGS rates, new raise constraints)
before the optimizer solves.

## Notebook Parameters Cell
```python
run_id         = ""   # The actual RunID to substitute for '{run_id}' placeholders
sql_statements = ""   # SQL statements delimited by ";\n" (semicolon + newline)
```

## Cell 1 — Parse and Execute Statements
```python
statements = [s.strip() for s in sql_statements.split(";\n") if s.strip()]

print(f"Executing {len(statements)} SQL statement(s) for RunID: {run_id}")

for i, stmt in enumerate(statements, 1):
    # Substitute the run_id placeholder
    resolved = stmt.replace("{run_id}", run_id)
    print(f"\n--- Statement {i} ---\n{resolved}\n")
    spark.sql(resolved)
    print(f"Statement {i}: OK")

print(f"\nAll {len(statements)} statement(s) executed successfully.")
```

## Cell 2 — Return
```python
mssparkutils.notebook.exit("ok")
```

---

## How SQL is passed from DE_NB_Main

```python
# In DE_NB_Main:
sql_statements = ";\n".join(intent["sql_mutations"])

mssparkutils.notebook.run(
    "DE_NB_Apply_Scenario",
    timeout_seconds=300,
    arguments={
        "run_id": new_run_id,
        "sql_statements": sql_statements
    }
)
```

## Example — what sql_statements looks like at runtime

```
UPDATE input_cogs
SET CogsRate = 0.25
WHERE RunID = '{run_id}'
  AND CustomerGroupID = 'C1'
  AND PeriodID = 85;
UPDATE input_investor_capital
SET InterestRate = 0.015
WHERE RunID = '{run_id}'
  AND InvestorCapitalID = 'Loan1'
```

After `replace("{run_id}", "abc-123-...")` each statement becomes executable Spark SQL.

## Notes
- SQL validation happens in `DE_NB_Main` BEFORE this notebook is called. This notebook
  trusts the input — do not add duplicate validation here.
- If any statement fails, `spark.sql()` raises an exception that propagates to `DE_NB_Main`.
- Statements execute in the order they appear in `sql_statements` — ordering matters for
  INSERT-then-UPDATE patterns.
