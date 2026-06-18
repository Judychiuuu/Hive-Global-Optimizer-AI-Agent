# DE_NB_Get_New_Run_Id — Tool Notebook Spec

## Purpose
Creates a new run by copying an existing run via `DE_NB_CopyRun`, then returns the new
RunID as a JSON string. Called by `DE_NB_Main` (Cell 5) before scenario changes are applied.

## Notebook Parameters Cell
```python
old_run_id_to_copy = ''
name               = 'Testing'
description        = 'This run used to test AI Agent'
duration           = 1351
user               = 'judy.chiu@hivefs.com'
```

## Cell 1 — Copy Run
```python
result = mssparkutils.notebook.run("DE_NB_CopyRun", timeout_seconds, {
    "old_run_id": old_run_id_to_copy,
    "name": name,
    "description": description,
    "duration": duration,
    "user": user
})

new_run_id = ast.literal_eval(result)['new_run_id']
new_run_id
```

## Cell 2 — Return
```python
mssparkutils.notebook.exit(json.dumps({"new_run_id": new_run_id}))
```

---

## How this notebook fits in the chain

Called by `DE_NB_Main` (Cell 5):
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
```

## Notes
- This notebook delegates the actual copy to `DE_NB_CopyRun` and acts as a thin wrapper
  that standardises the return format for `DE_NB_Main`.
- Cell 1 parses the `DE_NB_CopyRun` return value with `ast.literal_eval`; `DE_NB_Main`
  then parses this notebook's exit value with `json.loads` — both must remain consistent.
