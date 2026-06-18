# DE_NB_Main — Orchestrator Notebook Spec

## Purpose
Main entry point for the Hive Global Optimizer agent. Receives a natural language command,
calls the Claude API to parse intent (with schema validation retry), validates the result, and
executes the tool chain: DE_NB_Get_New_Run_Id → DE_NB_Apply_Scenario → DE_NB_RunModel.

## Notebook Parameters Cell
```python
user_command           = ""  # NL command, e.g. "update COGS for C1 to 25% in July 2024"
old_run_id             = ""  # UUID of the run to copy from (baseline scenario)
clarification_response = ""  # Leave empty on first run; fill in on re-run if clarification was requested
```

## Dependencies
- `anthropic` Python SDK
- `jsonschema` for schema validation
- `mssparkutils` for calling child notebooks
- Fabric lakehouse path to SKILL.md and `intent_schema.json`

---

## Cell 1 — Load SKILL.md
```python
with open("/lakehouse/default/Files/skills/hive-optimizer-nl-intent/SKILL.md") as f:
    raw_skill = f.read()

# Strip YAML frontmatter
if raw_skill.startswith("---"):
    end = raw_skill.find("---", 3)
    raw_skill = raw_skill[end + 3:].lstrip("\n") if end != -1 else raw_skill

# Strip ## Examples section to reduce token usage
examples_idx = raw_skill.find("## Examples")
skill_md = raw_skill[:examples_idx].rstrip() if examples_idx != -1 else raw_skill
```

## Cell 2 — Call LiteLLM API with Schema Validation Retry
```python
import litellm, json, jsonschema

MODEL = "anthropic/claude-sonnet-4-6"
MAX_RETRIES = 3

with open("/lakehouse/default/Files/skills/hive-optimizer-nl-intent/intent_schema.json") as f:
    schema = json.load(f)

SYSTEM_MESSAGE = {
    "role": "system",
    "content": [
        {
            "type": "text",
            "text": skill_md,
            "cache_control": {"type": "ephemeral"},
        }
    ],
}


def strip_fences(text):
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        text = text[text.index("\n") + 1:] if "\n" in text else text
        text = text.rsplit("```", 1)[0].strip()
    return text


# On re-run, append the user's clarification to the original command
if clarification_response:
    full_command = f"{user_command}\n\nUser clarification: {clarification_response}"
else:
    full_command = user_command

messages = [SYSTEM_MESSAGE, {"role": "user", "content": full_command}]
intent = None

for attempt in range(1, MAX_RETRIES + 1):
    print(f"Attempt {attempt}/{MAX_RETRIES}...")

    response = litellm.completion(
        model=MODEL,
        max_tokens=2048,
        messages=messages,
    )

    raw = strip_fences(response.choices[0].message.content)
    messages.append({"role": "assistant", "content": raw})

    try:
        intent = json.loads(raw)
        jsonschema.validate(instance=intent, schema=schema)
        print(f"Schema validation passed on attempt {attempt}.")
        break
    except json.JSONDecodeError as e:
        error_msg = f"Your response was not valid JSON: {e}\nRespond with raw JSON only, no markdown fences."
    except jsonschema.ValidationError as e:
        path = " -> ".join(str(p) for p in e.absolute_path) or "(root)"
        error_msg = (
            f"Your response failed JSON schema validation.\n"
            f"Field path: {path}\n"
            f"Error: {e.message}\n"
            f"Fix that field and respond with the corrected raw JSON only."
        )

    if attempt < MAX_RETRIES:
        print(f"Error on attempt {attempt}: {error_msg}")
        messages.append({"role": "user", "content": error_msg})
    else:
        raise RuntimeError(f"Schema validation failed after {MAX_RETRIES} attempts. Last error: {error_msg}")

print(json.dumps(intent, indent=2))
```

## Cell 3 — Handle Clarifications
```python
if intent["period_resolution_required"] or intent["confidence"] < 0.80:
    print("=== Clarification needed ===")
    print(f"\n{intent['plain_english']}\n")
    print("Please answer the following, then re-run with clarification_response filled in:\n")
    for i, q in enumerate(intent["ambiguities"], 1):
        print(f"  {i}. {q}")
    mssparkutils.notebook.exit(json.dumps({
        "status": "clarification_needed",
        "plain_english": intent["plain_english"],
        "questions": intent["ambiguities"]
    }))
```

## Cell 4 — SQL Validation
```python
ALLOWED_TABLES = {
    "input_cogs", "input_customer_capacities", "input_investor_capital",
    "input_performance_curves", "input_aggregated_raises", "input_aggregated_deployments",
    "input_fix_raises", "input_fix_deployments", "input_parameters",
    "input_investor_repayment_schedule", "input_net_new_capacities",
    "input_periods_config", "input_portfolios_config", "input_relative_deployments",
    "input_repeats_distribution", "input_time_periods"
}
ALLOWED_VERBS = {"UPDATE", "INSERT", "DELETE"}

def validate_sql(sql: str) -> None:
    upper = sql.strip().upper()
    verb = upper.split()[0]
    assert verb in ALLOWED_VERBS, f"Disallowed SQL verb '{verb}' — only UPDATE/INSERT/DELETE allowed"
    assert "{RUN_ID}" in upper or "RUNID" in upper, \
        f"SQL missing RunID condition: {sql[:80]}"
    assert any(t.upper() in upper for t in ALLOWED_TABLES), \
        f"SQL targets unknown or disallowed table: {sql[:80]}"

for stmt in intent["sql_mutations"]:
    validate_sql(stmt)
print(f"SQL validation passed ({len(intent['sql_mutations'])} statements).")
```

## Cell 5 — Get New RunID then CopyRun
```python
result = mssparkutils.notebook.run(
    "DE_NB_Get_New_Run_Id",
    timeout_seconds=60,
    arguments={
        "old_run_id": old_run_id_to_copy,
        "name": name,
        "description": description,
        "duration": duration,
        "user": user
    }
)
new_run_id = json.loads(result)["new_run_id"]
print(f"New RunID: {new_run_id}")
```

## Cell 6 — Apply Scenario
```python
if intent["sql_mutations"]:
    sql_statements = ";\n".join(intent["sql_mutations"])
    mssparkutils.notebook.run(
        "DE_NB_Apply_Scenario",
        timeout_seconds=300,
        arguments={
            "run_id": new_run_id,
            "sql_statements": sql_statements
        }
    )
    print(f"Apply_Scenario complete: {len(intent['sql_mutations'])} statements executed.")
else:
    print("No SQL mutations — skipping Apply_Scenario.")
```

## Cell 7 — Run Model
```python
mssparkutils.notebook.run(
    "DE_NB_RunModel",
    timeout_seconds=intent["run_params"]["timeout_seconds"] + 120,
    arguments={
        "run_id": new_run_id,
        "run_params": json.dumps(intent["run_params"])
    }
)
print(f"RunModel complete. Results are in RunID: {new_run_id}")
```

## Cell 8 — Return Result
```python
result = {
    "new_run_id": new_run_id,
    "plain_english": intent["plain_english"],
    "sql_mutations_applied": len(intent["sql_mutations"])
}
print(json.dumps(result, indent=2))
mssparkutils.notebook.exit(json.dumps(result))
```

---

## Error Handling Notes
- Cell 2 retries up to 3 times on JSON decode or schema validation errors, feeding the error
  message back to the model as a follow-up user message so the model can self-correct.
- Cell 3 (clarification) exits the notebook with a structured JSON payload instead of raising,
  so the caller can surface the questions to the user and re-run with `clarification_response` filled in.
- Cells 5–7 should each be wrapped in try/except in production to log failures with the
  `new_run_id` context before re-raising.
