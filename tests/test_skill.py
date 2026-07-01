# tests/test_skill.py
import sys
import litellm
from litellm.exceptions import RateLimitError
import json
import time
import jsonschema
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding='utf-8')

load_dotenv()

# Load skill — strip YAML frontmatter and examples to reduce token usage
with open("skills/hive-optimizer-nl-intent/SKILL.md", "r", encoding="utf-8") as f:
    raw_skill = f.read()

with open("skills/hive-optimizer-nl-intent/intent_schema.json", "r", encoding="utf-8") as f:
    INTENT_SCHEMA = json.load(f)

if raw_skill.startswith("---"):
    end = raw_skill.find("---", 3)
    raw_skill = raw_skill[end + 3:].lstrip("\n") if end != -1 else raw_skill

examples_idx = raw_skill.find("## Examples")
skill = raw_skill[:examples_idx].rstrip() if examples_idx != -1 else raw_skill

# ── Intent parser system message ────────────────────────────────────────────
INTENT_SYSTEM_MESSAGE = {
    "role": "system",
    "content": [
        {
            "type": "text",
            "text": f"""You are a database intent parser for the Hive Global Optimizer.

{skill}

Respond ONLY with a valid JSON object matching the output schema defined in the skill.
No preamble, no explanation, no markdown fences. Raw JSON only.""",
            "cache_control": {"type": "ephemeral"},
        }
    ],
}

# ── Scorer system message ────────────────────────────────────────────────────
SCORER_SYSTEM_MESSAGE = {
    "role": "system",
    "content": [
        {
            "type": "text",
            "text": """You are an objective evaluator of NL-to-DB intent parsing responses.

The response schema has these top-level fields:
  run_params        (always present — 10 optimizer notebook params with defaults)
  sql_mutations     (array of SQL strings — [] if no mutations needed)
  period_resolution_required, period_label, confidence, ambiguities, plain_english

Score the response against this rubric (12 points total):

1. run_params_optimizer (0-3): +1 per correct field among objective_function, duration, mip_gap, timeout_seconds, start_period (max 3); -1 per hallucinated value
2. run_params_identity (0-1): +1 if old_run_id_to_copy, name, description, user use placeholders unless user explicitly provided values; 0 if fabricated
3. sql_verb (0-1): +1 if only UPDATE/INSERT/DELETE verbs used in sql_mutations; 0 if SELECT appears or wrong verb; award 1 if no mutations are required
4. sql_table (0-1): +1 if SQL targets the correct table; 0 if wrong table; award 1 if no mutations are required
5. sql_values (0-2): +1 per correct field=value pair in the SQL (max 2); -1 per hallucinated column; award 2 if no mutations are required
6. sql_where (0-1): +1 if RunID placeholder ('{run_id}') is present on run-scoped tables AND PK columns are correct; 0 if missing; award 1 if no mutations are required
7. period_resolution_required (0-1): +1 if true only for year-only input (YYYY), false for YYYY-MM (with first-week default noted) and YYYY-MM-DD; 0 if wrong
8. confidence_calibrated (0-1): +1 if ambiguities non-empty when confidence < 0.80 AND empty when >= 0.80; 0 if misaligned
9. ambiguities_complete (0-1): +1 if all unit conversions, value granularity questions (monthly/yearly/weekly), and unresolved fields are flagged; 0 if any gap

Return ONLY a JSON object — no markdown fences, no preamble:
{
  "run_params_optimizer": <int 0-3>,
  "run_params_identity": <int 0-1>,
  "sql_verb": <int 0-1>,
  "sql_table": <int 0-1>,
  "sql_values": <int 0-2>,
  "sql_where": <int 0-1>,
  "period_resolution_required": <int 0-1>,
  "confidence_calibrated": <int 0-1>,
  "ambiguities_complete": <int 0-1>,
  "total": <int 0-12>,
  "notes": "<one sentence: what was deducted and why, or Full marks if 12/12>"
}""",
            "cache_control": {"type": "ephemeral"},
        }
    ],
}

# Haiku uses ~10x fewer tokens than Sonnet — critical for OAuth key quotas.
MODEL = "anthropic/claude-haiku-4-5-20251001"

# Delay between every API call (intent + scorer each count as one call).
INTER_CALL_DELAY = 15   # seconds between the intent call and the scorer call
INTER_PROMPT_DELAY = 15 # seconds between finishing one prompt and starting the next

test_prompts = [
    # Existing prompts (regression coverage)
    "OPEX is 12 million per year",
    "Cost per funded set at 58%",
    "Update the underwriting COGS rate for C1 to 25% in period 85",
    "Change the interest rate on Loan1 to 1.5%",
    "Show me the final bank balance and crossover point",

    # SQL generation: RunID placeholder and correct table targeting
    "Set the performance curve return rate for C1 to 0.12 in period 85",

    # Period resolution — YYYY-MM (month only, should default to first week, period_resolution_required=false)
    "Fix deployment for C1 in July 2024",
    "Update the COGS rate for C1 starting from March 2025",

    # Period resolution — YYYY (year only, must ask clarifying question, period_resolution_required=true)
    "Capital raised in 2027 is 80 million",
    "Set the capital raised in 2026 to 100 million",

    # Value granularity — missing time unit (should ask monthly/yearly/weekly)
    "Set the COGS rate to 10%",           # ambiguous — which COGS type AND what period range?
    "Update the overhead",                # ambiguous — no amount, no period

    # Multi-mutation: two changes in one command
    "Change interest rate on Loan1 to 1.5% and set MIP gap to 0.5%",
]


def call_with_retry(messages, label):
    """Call the model with exponential backoff. Returns the response or None on quota exhaustion."""
    for attempt in range(4):
        try:
            return litellm.completion(
                model=MODEL,
                max_tokens=700,
                messages=messages,
            )
        except RateLimitError as e:
            retry_after = 30 * (2 ** attempt)  # 30s, 60s, 120s, 240s
            try:
                header_val = getattr(getattr(e, "response", None), "headers", {}).get("retry-after")
                if header_val:
                    retry_after = max(int(header_val), retry_after)
            except Exception:
                pass
            if attempt < 3:
                print(f"  [{label}] Rate limited (attempt {attempt + 1}/4), retrying in {retry_after}s...")
                time.sleep(retry_after)
            else:
                print(f"  [{label}] SKIPPED — quota exhausted after 4 attempts. Waiting {retry_after}s.")
                time.sleep(retry_after)
                return None


def strip_fences(text):
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        text = text[text.index("\n") + 1:] if "\n" in text else text
        text = text.rsplit("```", 1)[0].strip()
    return text


def show_tokens(response, label):
    usage = getattr(response, "usage", None)
    if usage:
        details = getattr(usage, "prompt_tokens_details", None)
        cache_read = getattr(details, "cached_tokens", 0) or 0
        print(f"  [{label}] tokens in={usage.prompt_tokens} (cached={cache_read}) out={usage.completion_tokens}")


results = []
failed = []

for i, prompt in enumerate(test_prompts):
    print(f"\n{'='*60}")
    print(f"INPUT: {prompt}")
    print('='*60)

    # ── Step 1: intent call with schema validation retry loop ────────────────
    # The API does NOT auto-retry on schema failure — we implement that here.
    # On failure we append the validation error as a user turn so Claude can fix it.
    MAX_SCHEMA_RETRIES = 2
    messages = [INTENT_SYSTEM_MESSAGE, {"role": "user", "content": prompt}]
    parsed = None
    schema_passed = False

    for attempt in range(MAX_SCHEMA_RETRIES + 1):
        label = f"intent (attempt {attempt + 1}/{MAX_SCHEMA_RETRIES + 1})"
        intent_response = call_with_retry(messages, label=label)

        if intent_response is None:
            failed.append(prompt)
            break

        show_tokens(intent_response, label)
        raw = strip_fences(intent_response.choices[0].message.content)

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as e:
            print(f"  INVALID JSON (attempt {attempt + 1}): {e}")
            if attempt < MAX_SCHEMA_RETRIES:
                messages.append({"role": "assistant", "content": raw})
                messages.append({"role": "user", "content": f"Your response was not valid JSON: {e}. Respond with raw JSON only, no markdown fences."})
            continue

        try:
            jsonschema.validate(instance=parsed, schema=INTENT_SCHEMA)
            print(f"  Schema validation: PASSED (attempt {attempt + 1})")
            schema_passed = True
            break
        except jsonschema.ValidationError as e:
            path = " -> ".join(str(p) for p in e.absolute_path) or "(root)"
            print(f"  Schema validation: FAILED (attempt {attempt + 1}) at [{path}]: {e.message}")
            if attempt < MAX_SCHEMA_RETRIES:
                messages.append({"role": "assistant", "content": raw})
                messages.append({
                    "role": "user",
                    "content": (
                        f"Your response failed JSON schema validation.\n"
                        f"Field path: {path}\n"
                        f"Error: {e.message}\n"
                        f"Fix that field and respond with the corrected raw JSON only."
                    ),
                })

    if intent_response is None or parsed is None:
        results.append({"prompt": prompt, "response": None, "score": None, "error": "quota or parse failure"})
        if i < len(test_prompts) - 1:
            print(f"  Waiting {INTER_PROMPT_DELAY}s...")
            time.sleep(INTER_PROMPT_DELAY)
        continue

    if not schema_passed:
        print(f"  Schema validation: STILL FAILING after {MAX_SCHEMA_RETRIES + 1} attempts — proceeding with last output")

    print(json.dumps(parsed, indent=2))

    # ── Step 2: scorer call ──────────────────────────────────────────────────
    print(f"  Waiting {INTER_CALL_DELAY}s before scoring...")
    time.sleep(INTER_CALL_DELAY)

    scorer_user_msg = {
        "role": "user",
        "content": (
            f"Original user command: {prompt}\n\n"
            f"Parsed intent:\n{json.dumps(parsed, indent=2)}\n\n"
            f"Note: 'sql_mutations' is an array of SQL strings (not structured JSON). "
            f"Score sql_verb/sql_table/sql_values/sql_where based on the SQL content of those strings."
        ),
    }
    score_response = call_with_retry(
        [SCORER_SYSTEM_MESSAGE, scorer_user_msg],
        label="scorer",
    )

    score = None
    if score_response is not None:
        show_tokens(score_response, "scorer")
        raw_score = strip_fences(score_response.choices[0].message.content)
        try:
            score = json.loads(raw_score)
            print(f"  SCORE: {score.get('total', '?')}/12 — {score.get('notes', '')}")
        except json.JSONDecodeError as e:
            print(f"  SCORE parse failed: {e}\n  Raw: {raw_score}")

    results.append({"prompt": prompt, "response": parsed, "score": score})

    if i < len(test_prompts) - 1:
        print(f"  Waiting {INTER_PROMPT_DELAY}s before next prompt...")
        time.sleep(INTER_PROMPT_DELAY)

# ── Write timestamped results file ───────────────────────────────────────────
timestamp = time.strftime("%Y%m%d_%H%M%S")
output_path = f"tests/results_{timestamp}.json"
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2)
print(f"\nResults written to {output_path}")

if failed:
    print(f"\nSKIPPED ({len(failed)} prompts hit quota limit):")
    for p in failed:
        print(f"  - {p}")
