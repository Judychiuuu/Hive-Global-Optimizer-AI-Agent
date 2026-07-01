import streamlit as st

# ── SSL workaround ──────────────────────────────────────────────────────────────
# This conda env's OpenSSL build has a broken DER/cadata code path, so the default
# context (which loads the Windows trust store as DER) raises
# [ASN1: NOT_ENOUGH_DATA] at import time — breaking `import litellm`/aiohttp/requests.
# Force the working PEM path via certifi. Must run BEFORE importing litellm.
import ssl, certifi
def _use_certifi(self, purpose=ssl.Purpose.SERVER_AUTH):
    self.load_verify_locations(cafile=certifi.where())
ssl.SSLContext.load_default_certs = _use_certifi

import litellm
from litellm.exceptions import RateLimitError
import json
import re
import time
import requests
import jsonschema
import pandas as pd
from datetime import date, timedelta
from dotenv import load_dotenv
import os

load_dotenv(override=True)

try:
    import deltalake
    from azure.identity import AzureCliCredential, InteractiveBrowserCredential
    HAS_DB_DEPS = True
except ImportError:
    HAS_DB_DEPS = False

# ── Constants ─────────────────────────────────────────────────────────────────
TEST_RUN_ID = "dbc14f6d-b0f3-4556-b7e5-2e63b4037edc"
MODEL = "anthropic/claude-haiku-4-5-20251001"
MAX_CLARIFICATION_ROUNDS = 5

ALLOWED_TABLES = {
    "input_cogs", "input_customer_capacities", "input_investor_capital",
    "input_performance_curves", "input_aggregated_raises", "input_aggregated_deployments",
    "input_fix_raises", "input_fix_deployments", "input_parameters",
    "input_investor_repayment_schedule", "input_net_new_capacities",
    "input_periods_config", "input_portfolios_config", "input_relative_deployments",
    "input_repeats_distribution", "input_time_periods",
}
ALLOWED_VERBS = {"UPDATE", "DELETE"}

QUICK_PROMPTS = [
    "OPEX is 12 million per year",
    "Run a scenario where cogs is set to 50%",
    "Capital raised in 2027 is 80 million",
    "Run the scenario where unit margin is set to 35%",
]

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Hive Optimizer — NL Intent Parser",
    page_icon="🐝",
    layout="wide",
)

# ── Period lookup ─────────────────────────────────────────────────────────────
def _build_period_lookups() -> tuple[str, str]:
    """Compute (weekly_json, monthly_boundary_json) from Python date arithmetic.

    Used only as a fallback when the database is not configured or unavailable.
    Prefer _get_period_lookups(), which reads the actual input_time_periods table.
    """
    base = date(2017, 6, 5)
    rows = []
    month_bounds: dict[str, dict] = {}
    d, pid = base, 0
    while d.year <= 2029:
        if d.year >= 2024:
            rows.append({"PeriodID": pid, "PeriodLabel": d.strftime("%Y-%m-%d")})
            key = d.strftime("%Y-%m")
            if key not in month_bounds:
                month_bounds[key] = {"Month": key, "FirstPeriodID": pid, "LastPeriodID": pid}
            else:
                month_bounds[key]["LastPeriodID"] = pid
        d += timedelta(weeks=1)
        pid += 1
    monthly = list(month_bounds.values())
    return json.dumps(rows), json.dumps(monthly)


@st.cache_resource
def _load_period_data_from_db() -> "tuple[pd.DataFrame | None, str | None]":
    """Load input_time_periods from the actual Delta table for TEST_RUN_ID.

    Cached for the lifetime of the Streamlit server process. Returns (df, error).
    """
    if not _db_configured():
        return None, "Database not configured"
    return _query_df("SELECT * FROM input_time_periods")


def _build_period_lookups_from_df(df: "pd.DataFrame") -> tuple[str, str]:
    """Build (weekly_json, monthly_boundary_json) from an input_time_periods DataFrame.

    Mirrors _build_period_lookups() but uses real table data instead of arithmetic.
    Both the weekly and monthly tables are limited to 2024+ (matching the fallback).
    """
    df = df.sort_values("PeriodID").reset_index(drop=True)
    rows = []
    month_bounds: dict[str, dict] = {}
    for _, row in df.iterrows():
        label = str(row["PeriodLabel"])
        pid = int(row["PeriodID"])
        if label[:4] >= "2024":
            rows.append({"PeriodID": pid, "PeriodLabel": label})
            key = label[:7]  # YYYY-MM
            if key not in month_bounds:
                month_bounds[key] = {"Month": key, "FirstPeriodID": pid, "LastPeriodID": pid}
            else:
                month_bounds[key]["LastPeriodID"] = pid
    return json.dumps(rows), json.dumps(list(month_bounds.values()))


def _get_period_lookups() -> tuple[str, str]:
    """Return (weekly_json, monthly_boundary_json) from the actual DB, or computed fallback."""
    df, _err = _load_period_data_from_db()
    if df is not None and not df.empty:
        return _build_period_lookups_from_df(df)
    return _build_period_lookups()


def resolve_period_id(date_str: str, mode: str = "floor") -> int | None:
    """Resolve a date string to a PeriodID from the actual input_time_periods table.

    mode:
      "floor"      — largest PeriodID where PeriodLabel <= date_str (containing week)
      "first_week" — smallest PeriodID where PeriodLabel >= date_str (pass YYYY-MM-01)
      "last_week"  — largest PeriodID where PeriodLabel < date_str (pass next month's first day)

    Returns None if DB is not configured or no matching period is found.
    """
    df, _ = _load_period_data_from_db()
    if df is None or df.empty:
        return None
    df = df.sort_values("PeriodLabel")
    if mode == "floor":
        candidates = df[df["PeriodLabel"] <= date_str]
        return int(candidates.iloc[-1]["PeriodID"]) if not candidates.empty else None
    if mode == "first_week":
        candidates = df[df["PeriodLabel"] >= date_str]
        return int(candidates.iloc[0]["PeriodID"]) if not candidates.empty else None
    if mode == "last_week":
        candidates = df[df["PeriodLabel"] < date_str]
        return int(candidates.iloc[-1]["PeriodID"]) if not candidates.empty else None
    return None

# ── Load skill resources ───────────────────────────────────────────────────────
@st.cache_resource
def load_resources():
    with open("skills/hive-optimizer-nl-intent/SKILL.md", "r", encoding="utf-8") as f:
        raw = f.read()
    with open("skills/hive-optimizer-nl-intent/intent_schema.json", "r", encoding="utf-8") as f:
        schema = json.load(f)
    if raw.startswith("---"):
        end = raw.find("---", 3)
        raw = raw[end + 3:].lstrip("\n") if end != -1 else raw
    idx = raw.find("## Examples")
    skill = raw[:idx].rstrip() if idx != -1 else raw
    return skill, schema

SKILL_TEXT, INTENT_SCHEMA = load_resources()

@st.cache_resource
def _get_intent_system_message() -> dict:
    """Build the LLM system message, sourcing period data from the actual DB when available.

    Cached so the (potentially large) period JSON strings are assembled only once per
    server process. Falls back to Python-computed periods when DB is not configured.
    """
    period_json, month_json = _get_period_lookups()
    period_section = (
        "\n\n## Period Lookup Reference\n"
        "### Month Boundary Table (USE THIS for any month or year reference)\n"
        "Each entry gives the exact first and last PeriodID for that calendar month. "
        "A PeriodID refers to the Monday that starts that week. "
        "Use FirstPeriodID when the user means the start of a month/year; "
        "use LastPeriodID when they mean the end. "
        "Do NOT set period_resolution_required: true for any date in 2024–2029.\n\n"
        + month_json
        + "\n\n### Weekly Detail Table (reference only — use the month table above for lookups)\n"
        + period_json
    )
    return {
        "role": "system",
        "content": [
            {
                "type": "text",
                "text": (
                    "You are a database intent parser for the Hive Global Optimizer.\n\n"
                    + SKILL_TEXT
                    + period_section
                    + "\n\nCRITICAL SQL RULES — violating these will cause a hard failure:\n"
                    "1. Use ONLY UPDATE or DELETE statements in sql_mutations. Never use INSERT or SELECT.\n"
                    "   CopyRun has already created all rows for this RunID — only UPDATE or DELETE existing rows.\n"
                    "2. Every UPDATE must include WHERE RunID = '{RUN_ID}' as the first WHERE condition.\n"
                    "\n\nRespond ONLY with a valid JSON object matching the output schema defined in the skill.\n"
                    "No preamble, no explanation, no markdown fences. Raw JSON only."
                ),
                "cache_control": {"type": "ephemeral"},
            }
        ],
    }

# ── Fabric authentication & DB helpers ────────────────────────────────────────

def _acquire_token(scope: str) -> str | None:
    if not HAS_DB_DEPS:
        return None
    auth_method = os.getenv("FABRIC_AUTH_METHOD", "cli").lower()
    try:
        credential = (
            InteractiveBrowserCredential()
            if auth_method == "browser"
            else AzureCliCredential()
        )
        return credential.get_token(scope).token
    except Exception:
        return None


@st.cache_resource(ttl=3500)
def _get_cached_token() -> str | None:
    """Acquire a Fabric API token (for notebook runner API calls)."""
    return _acquire_token("https://analysis.windows.net/powerbi/api/.default")


@st.cache_resource(ttl=3500)
def _get_storage_token() -> str | None:
    """Acquire an Azure Storage token (for OneLake Delta table reads)."""
    return _acquire_token("https://storage.azure.com/.default")


def _onelake_path(table_name: str) -> str:
    workspace_name = os.getenv("FABRIC_WORKSPACE_NAME") or os.getenv("FABRIC_WORKSPACE_ID")
    lakehouse = os.getenv("FABRIC_DATABASE")
    return (
        f"abfss://{workspace_name}@onelake.dfs.fabric.microsoft.com"
        f"/{lakehouse}.Lakehouse/Tables/{table_name}"
    )


def _apply_extra_where(df: pd.DataFrame, where_text: str) -> pd.DataFrame:
    """Filter df by the non-RunID predicates in an already-resolved SQL WHERE clause."""
    def _to_num(s: str):
        return int(s) if "." not in s else float(s)

    for pred in re.split(r"\s+AND\s+(?=[A-Za-z_])", where_text.strip(), flags=re.IGNORECASE):
        pred = pred.strip()
        if re.match(r"RunID\s*=", pred, re.IGNORECASE):
            continue
        # BETWEEN
        m = re.match(r"(\w+)\s+BETWEEN\s+([\d.]+)\s+AND\s+([\d.]+)$", pred, re.IGNORECASE)
        if m:
            col = next((c for c in df.columns if c.lower() == m.group(1).lower()), None)
            if col:
                df = df[df[col].between(_to_num(m.group(2)), _to_num(m.group(3)))]
            continue
        # IN (...)
        m = re.match(r"(\w+)\s+IN\s*\(([\d,\s]+)\)$", pred, re.IGNORECASE)
        if m:
            col = next((c for c in df.columns if c.lower() == m.group(1).lower()), None)
            if col:
                df = df[df[col].isin([int(x.strip()) for x in m.group(2).split(",") if x.strip()])]
            continue
        # col = value
        m = re.match(r"(\w+)\s*=\s*(.+)$", pred, re.IGNORECASE)
        if m:
            col = next((c for c in df.columns if c.lower() == m.group(1).lower()), None)
            raw = m.group(2).strip().strip("'")
            if col:
                try:
                    val = _to_num(raw)
                except ValueError:
                    val = raw
                df = df[df[col] == val]
    return df


def _query_df(sql: str, run_id: str | None = None) -> tuple[pd.DataFrame | None, str | None]:
    """Parse a SELECT * FROM <table> [WHERE ...] statement and read via OneLake Delta."""
    m = re.match(
        r"SELECT\s+\*\s+FROM\s+(\w+)(?:\s+(WHERE\s+.+))?$",
        sql.strip(), re.IGNORECASE | re.DOTALL,
    )
    if not m:
        return None, f"Cannot parse table name from: {sql}"
    table_name = m.group(1)
    where_text = re.sub(r"^WHERE\s+", "", m.group(2) or "", flags=re.IGNORECASE).strip()

    workspace_id = os.getenv("FABRIC_WORKSPACE_ID")
    lakehouse = os.getenv("FABRIC_DATABASE")
    if not (workspace_id and lakehouse):
        return None, "FABRIC_WORKSPACE_ID or FABRIC_DATABASE not set in .env"

    token = _get_storage_token()
    if not token:
        return None, (
            "Cannot acquire OneLake storage token. "
            "Run `az login` in your terminal, or set FABRIC_AUTH_METHOD=browser in .env."
        )

    _run_id = run_id or TEST_RUN_ID
    try:
        dt = deltalake.DeltaTable(
            _onelake_path(table_name),
            storage_options={"account_name": "onelake", "bearer_token": token},
        )
        df = dt.to_pandas(filters=[("RunID", "=", _run_id)])
        if where_text:
            df = _apply_extra_where(df, where_text)
        return df, None
    except Exception as e:
        return None, str(e)


def _db_configured() -> bool:
    return HAS_DB_DEPS and bool(
        os.getenv("FABRIC_WORKSPACE_ID") and os.getenv("FABRIC_DATABASE")
    )


# ── SQL helpers ───────────────────────────────────────────────────────────────

def _inject_runid(sql: str) -> str:
    """Ensure UPDATE/DELETE statements have WHERE RunID = '{RUN_ID}'. Inserts it if missing."""
    stripped = sql.strip()
    upper = stripped.upper()
    verb = upper.split()[0] if stripped else ""
    if verb not in ("UPDATE", "DELETE"):
        return sql
    if re.search(r"RUNID\s*=\s*'\{RUN_?ID\}'", upper):
        return sql
    where_match = re.search(r'\bWHERE\b', stripped, re.IGNORECASE)
    if where_match:
        pos = where_match.end()
        return stripped[:pos] + " RunID = '{run_id}' AND" + stripped[pos:]
    return stripped.rstrip(';').rstrip() + "\nWHERE RunID = '{run_id}'"


def _run_params_to_sql(rp: dict) -> list[str]:
    """Generate a single UPDATE input_parameters SQL from the Step 3.3 form values.

    input_parameters is a wide table (one row per RunID, parameters as columns).
    DE_NB_RunModel reads it directly from the lakehouse — these UPDATEs are the
    only way form values reach the optimizer.
    """
    end_period = rp["start_period"] + rp["duration"]
    obj = rp["objective_function"]
    return [
        f"UPDATE input_parameters\n"
        f"SET StartPeriod = '{rp['start_period']}',\n"
        f"    EndPeriod = '{end_period}',\n"
        f"    MainObjectiveFunction = '{obj}',\n"
        f"    MIPGap = '{rp['mip_gap']}'\n"
        f"WHERE RunID = '{{run_id}}'"
    ]


def validate_sql(sql: str) -> str | None:
    """Returns an error string, or None if valid.

    Mirror of the check in DE_NB_Main / DE_NB_Update_Input — keep the three copies
    in sync. UPDATE/DELETE must be RunID-scoped via WHERE.
    """
    upper = sql.strip().upper()
    verb = upper.split()[0] if upper else ""
    if verb not in ALLOWED_VERBS:
        return f"Disallowed verb '{verb}' — only {'/'.join(sorted(ALLOWED_VERBS))} allowed"
    if verb in ("UPDATE", "DELETE"):
        if not re.search(r"WHERE\s+RUNID\s*=\s*'\{RUN_?ID\}'", upper):
            return f"Missing WHERE RunID = '{{run_id}}' — got: {sql[:120]}"
    if not any(t.upper() in upper for t in ALLOWED_TABLES):
        return f"No recognised table found in: {sql[:80]}"
    return None


# ── Conciseness rewrite (runs BEFORE the preview/confirm gate) ──────────────────
# Collapses multiple single-period UPDATEs (or a contiguous PeriodID IN list) into a
# single `PeriodID BETWEEN min AND max`, de-dupes SET assignments, and drops exact
# duplicate statements. Conservative by design: any statement it cannot confidently
# parse — including one that already uses BETWEEN or an arithmetic period bound — is
# passed through untouched, so the rewrite never silently widens a mutation's scope.

def _normalize_set(set_text: str) -> str:
    """De-dupe SET assignments (last write wins), return a canonical 'Col = val, …'."""
    assignments: dict[str, str] = {}
    for part in re.split(r",\s*(?=[A-Za-z_])", set_text.strip()):
        kv = part.split("=", 1)
        if len(kv) == 2:
            assignments[kv[0].strip()] = kv[1].strip()
    return ", ".join(f"{k} = {v}" for k, v in assignments.items())


def _parse_update(sql: str) -> dict | None:
    """Parse an UPDATE into {table, set, rest, periods}; None if not safely mergeable.

    `rest` is the list of non-PeriodID WHERE predicates (original text). `periods` is a
    set of ints when the only PeriodID predicate is `= N` or `IN (ints)`, else None
    (no PeriodID at all) — or the whole parse fails (returns None) for any PeriodID
    predicate we don't handle (BETWEEN, <, >, arithmetic), so it stays untouched.
    """
    m = re.match(
        r"\s*UPDATE\s+(\w+)\s+SET\s+(.*?)\s+WHERE\s+(.*)$",
        sql.strip(), re.IGNORECASE | re.DOTALL,
    )
    if not m:
        return None
    table, set_text, where_text = m.group(1), m.group(2).strip(), m.group(3).strip()
    periods: set[int] | None = None
    rest: list[str] = []
    for pred in re.split(r"\s+AND\s+", where_text, flags=re.IGNORECASE):
        pred = pred.strip()
        eq = re.match(r"PeriodID\s*=\s*(\d+)$", pred, re.IGNORECASE)
        inl = re.match(r"PeriodID\s+IN\s*\(([\d,\s]+)\)$", pred, re.IGNORECASE)
        if eq:
            periods = {int(eq.group(1))}
        elif inl:
            periods = {int(x) for x in inl.group(1).split(",") if x.strip()}
        elif re.search(r"PeriodID", pred, re.IGNORECASE):
            return None  # unhandled PeriodID form — leave the statement alone
        else:
            rest.append(pred)
    return {"table": table, "set": _normalize_set(set_text), "rest": rest, "periods": periods}


def _period_predicate(periods: set[int]) -> str:
    vals = sorted(periods)
    if len(vals) == 1:
        return f"PeriodID = {vals[0]}"
    if vals[-1] - vals[0] + 1 == len(vals):  # contiguous → BETWEEN
        return f"PeriodID BETWEEN {vals[0]} AND {vals[-1]}"
    return "PeriodID IN (" + ", ".join(str(v) for v in vals) + ")"


def _rebuild_update(parsed: dict, periods: set[int] | None) -> str:
    preds = list(parsed["rest"])
    if periods:
        preds.append(_period_predicate(periods))
    where = "\n  AND ".join(preds)
    return f"UPDATE {parsed['table']}\nSET {parsed['set']}\nWHERE {where}"


def make_concise(mutations: list[str]) -> tuple[list[str], list[str]]:
    """Return (rewritten_mutations, human_readable_notes)."""
    notes: list[str] = []
    seen_exact: set[str] = set()
    order: list[tuple[str, object]] = []   # ('group', key) | ('pass', sql), first-seen order
    groups: dict[tuple, dict] = {}

    for sql in mutations:
        exact = re.sub(r"\s+", " ", sql.strip()).upper()
        if exact in seen_exact:
            notes.append("Dropped an exact-duplicate statement.")
            continue
        seen_exact.add(exact)

        parsed = _parse_update(sql)
        if parsed is None or parsed["periods"] is None:
            # Not period-mergeable. If it parsed, rebuild to apply SET de-dup; else verbatim.
            order.append(("pass", _rebuild_update(parsed, None) if parsed else sql.strip()))
            continue

        key = (parsed["table"].lower(), parsed["set"],
               tuple(p.casefold() for p in parsed["rest"]))
        if key not in groups:
            groups[key] = {"parsed": parsed, "periods": set(parsed["periods"]), "count": 1}
            order.append(("group", key))
        else:
            groups[key]["periods"] |= parsed["periods"]
            groups[key]["count"] += 1

    out: list[str] = []
    for kind, val in order:
        if kind == "pass":
            out.append(val)  # type: ignore[arg-type]
            continue
        g = groups[val]  # type: ignore[index]
        out.append(_rebuild_update(g["parsed"], g["periods"]))
        pred = _period_predicate(g["periods"])
        if g["count"] > 1:
            notes.append(
                f"Merged {g['count']} per-period statements on "
                f"{g['parsed']['table']} into one ({pred})."
            )
        elif len(g["periods"]) > 1 and pred.upper().startswith("PERIODID BETWEEN"):
            notes.append(
                f"Collapsed PeriodID list on {g['parsed']['table']} into {pred}."
            )
    return out, notes


def assert_not_base_run(run_id: str, base_run_id: str | None = None) -> str | None:
    """Returns an error string if the target run is missing or is the baseline run.

    Orchestrator-side guard. The authoritative check (against the `runs` table) lives
    in DE_NB_Update_Input — this only catches the obvious 'mutating the run we copied
    from' mistake before anything is submitted.
    """
    if not run_id or not str(run_id).strip():
        return "No target run_id — refusing to execute."
    if base_run_id and str(run_id).strip() == str(base_run_id).strip():
        return "Target run_id equals the baseline run being copied from — refusing to mutate the baseline."
    return None


def _derive_preview_select(update_sql: str, run_id: str) -> str:
    m = re.match(
        r"UPDATE\s+(\w+)\s+SET\s+.+?\s+(WHERE\s+.+)$",
        update_sql.strip(), re.IGNORECASE | re.DOTALL,
    )
    if not m:
        raise ValueError(f"Cannot parse UPDATE: {update_sql!r}")
    table, where = m.group(1), m.group(2)
    resolved = where.replace("{RUN_ID}", run_id).replace("{run_id}", run_id)
    return f"SELECT * FROM {table} {resolved}"


def _parse_set_clause(sql: str) -> dict:
    m = re.match(r"UPDATE\s+\w+\s+SET\s+(.+?)\s+WHERE\s+", sql.strip(), re.IGNORECASE | re.DOTALL)
    if not m:
        return {}
    assignments = {}
    for part in re.split(r",\s*(?=[A-Za-z_])", m.group(1)):
        kv = part.split("=", 1)
        if len(kv) == 2:
            col = kv[0].strip()
            raw_val = kv[1].strip().strip("'")
            try:
                val = float(raw_val) if "." in raw_val else int(raw_val)
            except (ValueError, TypeError):
                val = raw_val
            assignments[col] = val
    return assignments


def _simulate_after(before_df: pd.DataFrame, set_map: dict) -> pd.DataFrame:
    after = before_df.copy()
    for col, val in set_map.items():
        matched = next((c for c in after.columns if c.lower() == col.lower()), None)
        if matched:
            after[matched] = val
    return after


def _changed_cols(before: pd.DataFrame, after: pd.DataFrame) -> list[str]:
    return [c for c in before.columns if c in after.columns and not before[c].equals(after[c])]


def _style_changed(df: pd.DataFrame, changed: list[str]):
    def _highlight(s):
        return (
            ["background-color: #d4edda; color: #155724"] * len(s)
            if s.name in changed else [""] * len(s)
        )
    return df.style.apply(_highlight, axis=0)


# ── LLM helpers ───────────────────────────────────────────────────────────────

def _md_safe(text: str) -> str:
    """Escape characters Streamlit's markdown treats specially.

    Most importantly, `$` triggers LaTeX math rendering (switching the font to
    a serif/italic KaTeX face). LLM output is full of dollar amounts, so escape
    every `$` to keep it in the normal body font.
    """
    return str(text).replace("$", "\\$")


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        text = text[text.index("\n") + 1:] if "\n" in text else text
        text = text.rsplit("```", 1)[0].strip()
    return text


def _call_with_retry(messages, label: str):
    for attempt in range(4):
        try:
            return litellm.completion(model=MODEL, max_tokens=2048, messages=messages)
        except RateLimitError as e:
            delay = 30 * (2 ** attempt)
            try:
                hdr = getattr(getattr(e, "response", None), "headers", {}).get("retry-after")
                if hdr:
                    delay = max(int(hdr), delay)
            except Exception:
                pass
            if attempt < 3:
                st.toast(f"Rate limited ({label}) — retrying in {delay}s…")
                time.sleep(delay)
            else:
                st.error(f"Quota exhausted for {label}.")
                return None
    return None


def _friendly_json_error(e: json.JSONDecodeError, raw: str) -> str:
    msg = str(e)
    if "Unterminated string" in msg or "Expecting" in msg and "EOF" in msg:
        return (
            "The model's response was cut off before it finished — "
            "the JSON is incomplete. Try rephrasing your request more concisely, "
            "or break it into two smaller requests."
        )
    if "Extra data" in msg:
        return "The model returned extra text after the JSON object. Retrying…"
    if "Expecting property name" in msg or "Expecting value" in msg:
        col = getattr(e, "colno", "?")
        return (
            f"The model produced malformed JSON near column {col}. "
            "This can happen with complex requests — retrying with a correction prompt."
        )
    return f"The model returned invalid JSON: {msg}"


def run_intent_call(messages, attempt_offset: int = 0):
    MAX_RETRIES = 2
    for attempt in range(MAX_RETRIES + 1):
        resp = _call_with_retry(messages, f"intent try {attempt + attempt_offset + 1}")
        if resp is None:
            return None, False
        raw = _strip_fences(resp.choices[0].message.content)
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as e:
            friendly = _friendly_json_error(e, raw)
            st.warning(f"Re-parse attempt {attempt + 1} failed — {friendly}")
            with st.expander(f"Raw model output (attempt {attempt + 1})", expanded=False):
                st.code(raw, language="json")
            if attempt < MAX_RETRIES:
                messages += [
                    {"role": "assistant", "content": raw},
                    {"role": "user", "content": f"Not valid JSON: {e}. Return raw JSON only."},
                ]
            continue
        try:
            jsonschema.validate(instance=parsed, schema=INTENT_SCHEMA)
            if parsed.get("sql_mutations"):
                parsed["sql_mutations"] = [_inject_runid(s) for s in parsed["sql_mutations"]]
            sql_errs = [err for stmt in (parsed.get("sql_mutations") or []) if (err := validate_sql(stmt))]
            if sql_errs:
                err_summary = "\n".join(f"- {e}" for e in sql_errs)
                st.warning(f"SQL validation errors (try {attempt + 1}):\n{err_summary}")
                if attempt < MAX_RETRIES:
                    messages += [
                        {"role": "assistant", "content": raw},
                        {"role": "user", "content": (
                            f"SQL validation failed:\n{err_summary}\n"
                            "Fix all sql_mutations: use only UPDATE statements and ensure every "
                            "statement includes WHERE RunID = '{RUN_ID}'. Return corrected raw JSON only."
                        )},
                    ]
                    continue
            return parsed, True
        except jsonschema.ValidationError as e:
            path = " -> ".join(str(p) for p in e.absolute_path) or "(root)"
            st.warning(f"Schema invalid [{path}]: {e.message} (try {attempt + 1})")
            if attempt < MAX_RETRIES:
                messages += [
                    {"role": "assistant", "content": raw},
                    {"role": "user", "content": (
                        f"Schema validation failed.\nField: {path}\nError: {e.message}\n"
                        "Fix and return corrected raw JSON only."
                    )},
                ]
    return None, False


# ── Fabric notebook runner (Step 4) ────────────────────────────────────────────

def run_fabric_notebook(notebook_env_key: str, parameters: dict) -> tuple[bool, str]:
    workspace_id = os.getenv("FABRIC_WORKSPACE_ID")
    notebook_id = os.getenv(notebook_env_key)
    if not (workspace_id and notebook_id):
        return False, f"Missing env var: FABRIC_WORKSPACE_ID or {notebook_env_key}"
    token = _get_cached_token()
    if not token:
        return False, "Cannot acquire Fabric token."
    url = (
        f"https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}"
        f"/items/{notebook_id}/jobs/instances?jobType=RunNotebook"
    )
    body = {
        "executionData": {
            "parameters": {k: {"value": str(v), "type": "string"} for k, v in parameters.items()}
        }
    }
    try:
        resp = requests.post(
            url, headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=body, timeout=30,
        )
        if resp.status_code in (200, 201, 202):
            location = resp.headers.get("Location", "(no location header)")
            return True, f"Job submitted. Poll status at: {location}"
        return False, f"API {resp.status_code}: {resp.text[:300]}"
    except Exception as e:
        return False, str(e)


def _get_new_run_id_from_fabric(
    name: str,
    description: str,
    user: str,
    duration: int,
    timeout_seconds: int,
    max_wait: int = 360,
) -> tuple[str | None, str | None]:
    """Submit DE_NB_Get_New_Run_Id, poll until done, return (new_run_id, error)."""
    workspace_id = os.getenv("FABRIC_WORKSPACE_ID")
    notebook_id = os.getenv("FABRIC_NOTEBOOK_GET_NEW_RUN_ID")
    if not (workspace_id and notebook_id):
        return None, "Missing FABRIC_WORKSPACE_ID or FABRIC_NOTEBOOK_GET_NEW_RUN_ID in .env"

    token = _get_cached_token()
    if not token:
        return None, "Cannot acquire Fabric token — run `az login` or set FABRIC_AUTH_METHOD=browser."

    url = (
        f"https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}"
        f"/items/{notebook_id}/jobs/instances?jobType=RunNotebook"
    )
    body = {
        "executionData": {
            "parameters": {
                "name":            {"value": name,              "type": "string"},
                "description":     {"value": description,       "type": "string"},
                "duration":        {"value": str(duration),     "type": "string"},
                "user":            {"value": user,              "type": "string"},
                "timeout_seconds": {"value": str(timeout_seconds), "type": "string"},
            }
        }
    }
    try:
        resp = requests.post(
            url,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=body, timeout=30,
        )
        if resp.status_code not in (200, 201, 202):
            return None, f"Submit failed (HTTP {resp.status_code}): {resp.text[:300]}"
        location = resp.headers.get("Location")
        if not location:
            return None, "No Location header returned — cannot poll job status."
    except Exception as e:
        return None, str(e)

    # Poll until Completed/Failed
    deadline = time.time() + max_wait
    while time.time() < deadline:
        try:
            poll = requests.get(
                location,
                headers={"Authorization": f"Bearer {token}"},
                timeout=30,
            )
            if poll.status_code != 200:
                return None, f"Poll failed (HTTP {poll.status_code}): {poll.text[:200]}"
            data = poll.json()
            status = data.get("status", "")
            if status == "Completed":
                # The Fabric Job Instance REST API does not return the notebook exit value —
                # mssparkutils.notebook.exit() is only accessible via mssparkutils.notebook.run().
                # Read the newly-created RunID directly from the runs Delta table instead.
                try:
                    storage_token = _get_storage_token() or _get_cached_token()
                    if not storage_token:
                        return None, "Job completed but cannot acquire a token to read result — run `az login` and retry."
                    dt = deltalake.DeltaTable(
                        _onelake_path("runs"),
                        storage_options={"account_name": "onelake", "bearer_token": storage_token},
                    )
                    df = dt.to_pandas()
                    matched = df[df["Name"] == name]
                    if "User" in matched.columns:
                        matched = matched[matched["User"] == user]
                    if matched.empty:
                        return None, f"Job completed but no run named '{name}' found in runs table."
                    if "Date" in matched.columns:
                        matched = matched.sort_values("Date", ascending=False)
                    new_run_id = str(matched.iloc[0]["RunID"])
                    return new_run_id, None
                except Exception as e:
                    return None, f"Job completed but could not read new_run_id from runs table: {e}"
            if status in ("Failed", "Cancelled", "Deduped"):
                reason = data.get("failureReason") or {}
                msg = reason.get("message") if isinstance(reason, dict) else str(reason)
                return None, f"Job {status}: {msg or '(no reason)'}"
            # InProgress / NotStarted — keep polling
        except Exception as e:
            return None, str(e)
        time.sleep(10)

    return None, f"Timed out after {max_wait}s waiting for DE_NB_Get_New_Run_Id."


# ── Session state ─────────────────────────────────────────────────────────────
# stage: "input" | "clarifying" | "validated" | "confirmed"
_DEFAULTS = {
    "stage": "input",
    "messages": [],
    "intent": None,
    "sql_errors": [],
    "user_command": "",
    "clarification_round": 0,
    "preview_loaded": False,
    "preview_data": [],      # list of dicts per mutation
    "preview_confirmed": False,
    "concise_notes": [],     # human-readable notes from the conciseness rewrite
    "history": [],
    "rp_description": "",
    "rp_name": "",
    "rp_user": "",
    "rp_objective_function": "Maximize Bank Balance",
    "rp_timeout_seconds": 600,
    "rp_duration": 769,
    "rp_mip_gap": 0.001,
    "rp_start_period": 461,
    "run_id": TEST_RUN_ID,
    "run_id_mode": "custom",  # "fabric" | "custom"
}
_DEFAULTS_VERSION = 3
if st.session_state.get("_defaults_version") != _DEFAULTS_VERSION:
    for _k, _v in _DEFAULTS.items():
        st.session_state[_k] = _v
    st.session_state["_defaults_version"] = _DEFAULTS_VERSION
    st.rerun()
else:
    for _k, _v in _DEFAULTS.items():
        if _k not in st.session_state:
            st.session_state[_k] = _v


def reset_flow():
    for k, v in _DEFAULTS.items():
        st.session_state[k] = v


def advance_to_validated():
    """Pre-execution safety step, then move into the Preview stage.

    Runs the conciseness rewrite on the intent's mutations *before* the preview/confirm
    gate so the user reviews and approves exactly what will execute. Keep this in lockstep
    with the equivalent cell in DE_NB_Main.
    """
    intent = st.session_state.intent or {}
    mutations = intent.get("sql_mutations") or []
    if mutations:
        rewritten, notes = make_concise(mutations)
        intent["sql_mutations"] = rewritten
        st.session_state.intent = intent
        st.session_state.concise_notes = notes
    else:
        st.session_state.concise_notes = []
    st.session_state.stage = "validated"


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Settings")

    if _db_configured():
        auth_method = os.getenv("FABRIC_AUTH_METHOD", "cli").upper()
        st.success(f"Database: Configured ✓ (auth: {auth_method})")
        period_df, period_err = _load_period_data_from_db()
        if period_df is not None and not period_df.empty:
            st.success(f"Period data: Live from `input_time_periods` ({len(period_df)} rows)")
        else:
            st.warning(f"Period data: Computed fallback — DB query failed: {period_err}")
    elif not HAS_DB_DEPS:
        st.warning("Database: Install deltalake + azure-identity\n`conda install -c conda-forge deltalake azure-identity`")
        st.caption("Period data: Computed fallback (no DB)")
    else:
        st.warning("Database: Not configured\n(Step 3.3 preview disabled)")
        st.caption("Period data: Computed fallback (DB not configured)")

    st.divider()
    st.subheader("Active Run ID")
    st.code(st.session_state.get("run_id", TEST_RUN_ID))
    _id_mode = st.session_state.get("run_id_mode", "custom")
    st.caption(f"Source: {'Fabric (new)' if _id_mode == 'fabric' else 'Custom / test'}")

    st.divider()
    st.subheader("Quick Prompts")
    st.caption("Click to pre-fill.")
    for tp in QUICK_PROMPTS:
        if st.button(tp, use_container_width=True, key=f"qp_{tp[:30]}"):
            reset_flow()
            st.session_state.user_command = tp
            st.rerun()

# ── Header & progress ─────────────────────────────────────────────────────────
st.title("🐝 Hive Global Optimizer")
st.markdown("**Natural Language → Database Intent Parser**")

_STAGE_LABELS = [
    ("input",     "1 Parse"),
    ("clarifying","2 Clarify"),
    ("validated", "3 Preview"),
    ("confirmed", "4 Execute"),
]
_stage_order = [s for s, _ in _STAGE_LABELS]
_cur_idx = _stage_order.index(st.session_state.stage) if st.session_state.stage in _stage_order else 0

_step_html_parts = []
for _i, (_, _label) in enumerate(_STAGE_LABELS):
    if _i < _cur_idx:
        _style = (
            "flex:1;padding:14px 8px;text-align:center;background:#28a745;color:#fff;"
            "border-radius:6px;font-weight:700;font-size:0.9rem;"
        )
        _text = f"✓ {_label}"
    elif _i == _cur_idx:
        _style = (
            "flex:1;padding:14px 8px;text-align:center;background:#0d6efd;color:#fff;"
            "border-radius:6px;font-weight:700;font-size:0.9rem;"
            "box-shadow:0 0 0 4px rgba(13,110,253,0.25);"
        )
        _text = f"● {_label}"
    else:
        _style = (
            "flex:1;padding:14px 8px;text-align:center;background:#e9ecef;color:#6c757d;"
            "border-radius:6px;font-size:0.9rem;"
        )
        _text = _label
    _step_html_parts.append(f'<div style="{_style}">{_text}</div>')

_progress_html = (
    '<div style="display:flex;gap:6px;margin:1rem 0 1.5rem 0;">'
    + "".join(_step_html_parts)
    + "</div>"
)
st.markdown(_progress_html, unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# Step 1: Parse
# ─────────────────────────────────────────────────────────────────────────────
st.subheader("Step 1: Parse")

with st.form("input_form"):
    cmd_val = st.text_input(
        "Enter your optimization command:",
        value=st.session_state.user_command,
        placeholder="e.g. OPEX is 12 million per year",
    )
    c1, c2 = st.columns([4, 1])
    with c1:
        submitted = st.form_submit_button("Parse Intent →", type="primary", use_container_width=True)
    with c2:
        reset_btn = st.form_submit_button("Reset", use_container_width=True)

if reset_btn:
    reset_flow()
    st.rerun()

if submitted and cmd_val.strip():
    reset_flow()
    st.session_state.user_command = cmd_val.strip()

    msgs = [_get_intent_system_message(), {"role": "user", "content": cmd_val.strip()}]
    st.session_state.messages = msgs

    with st.spinner("Parsing intent…"):
        intent, _ = run_intent_call(msgs)

    if intent is None:
        st.error("Intent parsing failed — check your API key / rate limit.")
        st.stop()

    st.session_state.intent = intent

    needs_clar = (
        bool(intent.get("ambiguities"))
        or intent.get("period_resolution_required", False)
        or intent.get("confidence", 1.0) < 0.9
    )
    st.session_state.clarification_round = 1 if needs_clar else 0
    if needs_clar:
        st.session_state.stage = "clarifying"
    else:
        advance_to_validated()
    st.rerun()

# ─────────────────────────────────────────────────────────────────────────────
# Show parsed intent (all stages after input)
# ─────────────────────────────────────────────────────────────────────────────
if st.session_state.intent and st.session_state.stage != "input":
    intent = st.session_state.intent
    st.divider()
    st.subheader("📋 Parsed Intent")

    m1, m2, m3 = st.columns(3)
    m1.metric("Confidence", f"{intent.get('confidence', 0):.0%}")
    m2.metric("Period Resolution Required", "Yes" if intent.get("period_resolution_required") else "No")
    m3.metric("SQL Mutations", len(intent.get("sql_mutations") or []))

    if intent.get("plain_english"):
        st.info(f"**In plain English:** {_md_safe(intent['plain_english'])}")

    mutations = intent.get("sql_mutations") or []
    if mutations:
        with st.expander(f"SQL Mutations ({len(mutations)})", expanded=True):
            for _i, _sql in enumerate(mutations, 1):
                st.markdown(f"**Mutation {_i}**")
                st.code(_sql, language="sql")

    with st.expander("Full JSON", expanded=False):
        st.json(intent)

# ─────────────────────────────────────────────────────────────────────────────
# Step 2: Clarify
# ─────────────────────────────────────────────────────────────────────────────
if st.session_state.stage == "clarifying":
    intent = st.session_state.intent
    ambiguities = intent.get("ambiguities") or []
    round_num = st.session_state.clarification_round

    st.divider()
    st.subheader(f"Step 2: Clarify (Round {round_num}/{MAX_CLARIFICATION_ROUNDS})")

    st.warning("The model flagged ambiguities. Answer below to improve the result:")
    for _i, _q in enumerate(ambiguities, 1):
        st.markdown(f"**{_i}.** {_md_safe(_q)}")

    with st.form("clarification_form"):
        answer = st.text_area("Your answers:", placeholder="e.g. The period runs from 2027-01-04 to 2027-03-29 (weeks 1–13 of 2027).", height=80)
        c1, c2 = st.columns(2)
        with c1:
            clarify_btn = st.form_submit_button("Submit & Re-parse →", type="primary", use_container_width=True)
        with c2:
            skip_btn = st.form_submit_button("Skip →", use_container_width=True)

    if clarify_btn and answer.strip():
        msgs = st.session_state.messages + [
            {"role": "assistant", "content": json.dumps(intent)},
            {"role": "user", "content": (
                f"Here are my answers:\n{answer}\n\n"
                "Please update your response with this information and return the revised JSON."
            )},
        ]
        with st.spinner("Re-parsing…"):
            clarified, _ = run_intent_call(msgs, attempt_offset=3)

        final = clarified if clarified is not None else intent
        st.session_state.intent = final
        st.session_state.messages = msgs

        needs_more = (
            (
                bool(final.get("ambiguities"))
                or final.get("period_resolution_required", False)
                or final.get("confidence", 1.0) < 0.9
            )
            and round_num < MAX_CLARIFICATION_ROUNDS
        )
        if needs_more:
            st.session_state.clarification_round += 1
        else:
            advance_to_validated()
        st.rerun()

    if skip_btn:
        advance_to_validated()
        st.rerun()

# ─────────────────────────────────────────────────────────────────────────────
# Step 3.1: SQL Validation  (shown from "validated" stage onwards)
# ─────────────────────────────────────────────────────────────────────────────
if st.session_state.stage in ("validated", "confirmed"):
    intent = st.session_state.intent
    mutations = intent.get("sql_mutations") or []

    st.divider()
    st.subheader("Step 3.1: SQL Validation")

    sql_errors = [e for stmt in mutations if (e := validate_sql(stmt))]

    if not mutations:
        st.info("No SQL mutations — validation passed (nothing to validate).")
    elif sql_errors:
        st.error(f"SQL validation failed ({len(sql_errors)} error{'s' if len(sql_errors) > 1 else ''}):")
        for err in sql_errors:
            st.markdown(f"- {err}")
    else:
        st.success(f"SQL validation passed — {len(mutations)} statement{'s' if len(mutations) != 1 else ''} OK.")

    if st.session_state.get("concise_notes"):
        st.caption("✂️ Conciseness rewrite applied before preview:")
        for _note in st.session_state.concise_notes:
            st.caption(f"• {_note}")

    st.session_state.sql_errors = sql_errors

# ─────────────────────────────────────────────────────────────────────────────
# Step 3.2: Run Parameters
# ─────────────────────────────────────────────────────────────────────────────
if st.session_state.stage in ("validated", "confirmed"):
    st.divider()
    st.subheader("Step 3.2: Run Parameters")
    st.caption("Fill in the required fields (*). Optimizer parameters are pre-filled with defaults — expand only if you need to change them for this run.")

    with st.form("run_params_form"):
        _rc1, _rc2, _rc3 = st.columns(3)
        with _rc1:
            _rp_description = st.text_input("Description *", value=st.session_state.rp_description, placeholder="e.g. Q3 scenario with increased OPEX")
        with _rc2:
            _rp_name = st.text_input("Name *", value=st.session_state.rp_name, placeholder="e.g. Q3_High_OPEX")
        with _rc3:
            _rp_user = st.text_input("User *", value=st.session_state.rp_user, placeholder="e.g. judy.chiu@hivefs.com")

        _end_period = st.session_state.rp_start_period + st.session_state.rp_duration
        with st.expander(
            f"⚙️ Optimizer Parameters — StartPeriod={st.session_state.rp_start_period}, "
            f"EndPeriod={_end_period}, MIPGap={st.session_state.rp_mip_gap}, "
            f"TimeoutSeconds={st.session_state.rp_timeout_seconds}",
            expanded=False,
        ):
            st.caption("Pre-filled with defaults. Only change if needed for this specific run.")
            _oc1, _oc2 = st.columns(2)
            with _oc1:
                _rp_objective = st.selectbox(
                    "Objective Function",
                    ["Maximize Bank Balance", "Minimize Crossover Point"],
                    index=0 if st.session_state.rp_objective_function == "Maximize Bank Balance" else 1,
                )
                _rp_start_period = st.text_input("Start Period", value=str(st.session_state.rp_start_period))
                _rp_duration = st.text_input("Duration (periods)", value=str(st.session_state.rp_duration))
                st.caption(f"→ EndPeriod = {st.session_state.rp_start_period} + {st.session_state.rp_duration} = **{_end_period}**")
            with _oc2:
                _rp_mip_gap = st.text_input("MIP Gap", value=str(st.session_state.rp_mip_gap))
                _rp_timeout = st.text_input("Timeout Seconds", value=str(st.session_state.rp_timeout_seconds))

        if st.form_submit_button("Save Run Parameters", use_container_width=True):
            st.session_state.rp_description = _rp_description
            st.session_state.rp_name = _rp_name
            st.session_state.rp_user = _rp_user
            st.session_state.rp_objective_function = _rp_objective
            try:
                st.session_state.rp_start_period = int(_rp_start_period)
            except ValueError:
                pass
            try:
                st.session_state.rp_duration = int(_rp_duration)
            except ValueError:
                pass
            try:
                st.session_state.rp_mip_gap = float(_rp_mip_gap)
            except ValueError:
                pass
            try:
                st.session_state.rp_timeout_seconds = int(_rp_timeout)
            except ValueError:
                pass
            st.session_state.preview_loaded = False
            st.session_state.preview_data = []

    _rp_required_missing = [
        f.replace("rp_", "")
        for f in ("rp_description", "rp_name", "rp_user")
        if not st.session_state.get(f, "").strip()
    ]
    if _rp_required_missing:
        st.warning(f"Required fields not yet filled: **{', '.join(_rp_required_missing)}**")

# ─────────────────────────────────────────────────────────────────────────────
# Step 3.3: Run ID
# ─────────────────────────────────────────────────────────────────────────────
if st.session_state.stage in ("validated", "confirmed"):
    st.divider()
    st.subheader("Step 3.3: Run ID")

    _mode_options = ["📡 Get new Run ID from Fabric (DE_NB_Get_New_Run_Id)", "✏️ Use existing / custom Run ID"]
    _mode_radio = st.radio(
        "Run ID source:",
        _mode_options,
        index=0 if st.session_state.run_id_mode == "fabric" else 1,
        horizontal=True,
        key="run_id_mode_radio",
    )
    _is_fabric_mode = _mode_radio == _mode_options[0]
    _new_mode = "fabric" if _is_fabric_mode else "custom"
    if st.session_state.run_id_mode != _new_mode:
        st.session_state.run_id_mode = _new_mode
        st.session_state.preview_loaded = False
        st.session_state.preview_data = []
        st.rerun()

    if _is_fabric_mode:
        # Required params come from Step 3.2 session state
        _fab_name = st.session_state.get("rp_name", "").strip()
        _fab_desc = st.session_state.get("rp_description", "").strip()
        _fab_user = st.session_state.get("rp_user", "").strip()
        _fab_dur  = st.session_state.get("rp_duration", 1351)
        _fab_tmo  = st.session_state.get("rp_timeout_seconds", 600)
        _params_ready = bool(_fab_name and _fab_desc and _fab_user)
        _nb_configured = bool(os.getenv("FABRIC_NOTEBOOK_GET_NEW_RUN_ID"))

        if not _nb_configured:
            st.warning("`FABRIC_NOTEBOOK_GET_NEW_RUN_ID` not set in .env — add the notebook item ID.")
        if not _params_ready:
            st.info("Fill in **Name**, **Description**, and **User** in Step 3.2 Run Parameters above first, then get a new Run ID here.")
        else:
            st.caption(
                f"Will call **DE_NB_Get_New_Run_Id** with: "
                f"name=`{_fab_name}`, user=`{_fab_user}`, duration=`{_fab_dur}`, timeout=`{_fab_tmo}`"
            )

        _already_obtained = (
            st.session_state.run_id_mode == "fabric"
            and st.session_state.run_id != TEST_RUN_ID
        )
        if _already_obtained:
            st.success(f"Run ID obtained: `{st.session_state.run_id}`")
            if st.button("🔄 Get another new Run ID", disabled=not (_params_ready and _nb_configured)):
                st.session_state.run_id = TEST_RUN_ID
                st.session_state.preview_loaded = False
                st.session_state.preview_data = []
                st.rerun()
        else:
            if st.button(
                "📡 Get new Run ID from Fabric",
                type="primary",
                disabled=not (_params_ready and _nb_configured),
                key="btn_get_run_id",
            ):
                with st.spinner("Calling DE_NB_Get_New_Run_Id — this can take 1–3 minutes…"):
                    _new_id, _err = _get_new_run_id_from_fabric(
                        name=_fab_name,
                        description=_fab_desc,
                        user=_fab_user,
                        duration=_fab_dur,
                        timeout_seconds=_fab_tmo,
                    )
                if _err:
                    st.error(f"Failed to get new Run ID: {_err}")
                else:
                    st.session_state.run_id = _new_id
                    st.session_state.preview_loaded = False
                    st.session_state.preview_data = []
                    st.rerun()

    else:  # custom mode
        with st.form("run_id_form"):
            _custom_id = st.text_input(
                "Run ID:",
                value=st.session_state.run_id,
                placeholder="e.g. dbc14f6d-b0f3-4556-b7e5-2e63b4037edc",
            )
            if st.form_submit_button("Use this Run ID"):
                _clean_id = _custom_id.strip()
                if _clean_id:
                    if st.session_state.run_id != _clean_id:
                        st.session_state.run_id = _clean_id
                        st.session_state.preview_loaded = False
                        st.session_state.preview_data = []
                    st.rerun()
        st.info(f"Active Run ID: `{st.session_state.run_id}`")

# ─────────────────────────────────────────────────────────────────────────────
# Step 3.4: Preview — Before / After comparison
# ─────────────────────────────────────────────────────────────────────────────
if st.session_state.stage in ("validated", "confirmed"):
    intent = st.session_state.intent
    mutations = intent.get("sql_mutations") or []
    sql_ok = not st.session_state.sql_errors

    # Build run params SQL for preview (same as Step 4.1)
    _rp_for_preview = {
        "description": st.session_state.get("rp_description", ""),
        "name": st.session_state.get("rp_name", ""),
        "user": st.session_state.get("rp_user", ""),
        "objective_function": st.session_state.get("rp_objective_function", "Maximize Bank Balance"),
        "timeout_seconds": st.session_state.get("rp_timeout_seconds", 600),
        "duration": st.session_state.get("rp_duration", 1351),
        "mip_gap": st.session_state.get("rp_mip_gap", 0.001),
        "start_period": st.session_state.get("rp_start_period", 461),
    }
    _form_mutations = _run_params_to_sql(_rp_for_preview)
    # Run params SQL first, then NL intent mutations
    _all_preview_stmts = [(s, "Run Parameters") for s in _form_mutations] + [(s, "NL Intent") for s in mutations]

    st.divider()
    st.subheader("Step 3.4: Preview — Review Changes Before Applying")

    if not sql_ok:
        st.error("Fix the SQL validation errors above before previewing.")

    else:
        # Load preview data once (triggered by run ID change or run params save)
        if not st.session_state.preview_loaded:
            preview_data = []
            db_ok = _db_configured()

            _preview_run_id = st.session_state.run_id
            with st.spinner("Loading current data from Lakehouse…"):
                for stmt, source in _all_preview_stmts:
                    upper = stmt.strip().upper()
                    _table_m = re.match(
                        r"(?:UPDATE|DELETE\s+FROM)\s+(\w+)",
                        stmt.strip(), re.IGNORECASE,
                    )
                    entry = {
                        "sql": stmt, "verb": upper.split()[0],
                        "table": _table_m.group(1) if _table_m else "unknown",
                        "before_df": None, "after_df": None,
                        "changed_cols": [], "set_map": {}, "error": None,
                        "source": source,
                    }

                    if not db_ok:
                        entry["error"] = (
                            "Database not configured — install pyodbc + msal and add "
                            "FABRIC_* vars to .env to enable live preview."
                        )
                        if upper.startswith("UPDATE"):
                            entry["set_map"] = _parse_set_clause(stmt)
                    elif upper.startswith("UPDATE"):
                        try:
                            sel = _derive_preview_select(stmt, _preview_run_id)
                            before_df, err = _query_df(sel, run_id=_preview_run_id)
                            if err:
                                entry["error"] = err
                            else:
                                set_map = _parse_set_clause(stmt)
                                after_df = _simulate_after(before_df, set_map)
                                entry.update({
                                    "before_df": before_df,
                                    "after_df": after_df,
                                    "set_map": set_map,
                                    "changed_cols": _changed_cols(before_df, after_df),
                                })
                        except Exception as e:
                            entry["error"] = str(e)
                    elif upper.startswith("DELETE"):
                        try:
                            tbl = re.match(r"DELETE\s+FROM\s+(\w+)", stmt, re.IGNORECASE)
                            whr = re.search(r"(WHERE\s+.+)$", stmt, re.IGNORECASE | re.DOTALL)
                            if tbl and whr:
                                sel = f"SELECT * FROM {tbl.group(1)} {whr.group(1)}"
                                sel = sel.replace("{RUN_ID}", _preview_run_id).replace("{run_id}", _preview_run_id)
                                before_df, err = _query_df(sel, run_id=_preview_run_id)
                                entry["before_df"] = before_df
                                entry["error"] = err
                        except Exception as e:
                            entry["error"] = str(e)
                    else:
                        entry["error"] = f"Unsupported verb '{entry['verb']}' — only UPDATE and DELETE are allowed."

                    preview_data.append(entry)

            st.session_state.preview_data = preview_data
            st.session_state.preview_loaded = True

        # ── Display each mutation's preview ──────────────────────────────────
        for idx, entry in enumerate(st.session_state.preview_data, 1):
            total = len(st.session_state.preview_data)
            with st.expander(
                f"Mutation {idx}/{total} — {entry.get('source', 'NL Intent')}: {entry['verb']} {entry['table']}",
                expanded=True,
            ):
                st.code(entry["sql"], language="sql")

                if entry["error"] and entry["before_df"] is None:
                    st.warning(f"Preview unavailable: {entry['error']}")
                    if entry["set_map"]:
                        st.markdown("**Columns that will be changed (values from SQL):**")
                        for col, val in entry["set_map"].items():
                            st.markdown(f"- `{col}` → `{val}`")
                    continue

                verb = entry["verb"]

                if verb == "UPDATE":
                    set_map = entry["set_map"]
                    changed = entry["changed_cols"]
                    before_df = entry["before_df"]
                    after_df = entry["after_df"]

                    # Summary of what changes
                    if set_map and before_df is not None and len(before_df) > 0:
                        st.markdown("**What will change:**")
                        for col, new_val in set_map.items():
                            db_col = next(
                                (c for c in before_df.columns if c.lower() == col.lower()), None
                            )
                            if db_col and db_col in before_df.columns:
                                old_val = before_df[db_col].iloc[0]
                                st.markdown(f"- **{db_col}**: `{old_val}` → `{new_val}`")
                            else:
                                st.markdown(f"- **{col}**: → `{new_val}` *(column not found in current data)*")
                    elif before_df is not None and len(before_df) == 0:
                        st.warning(
                            f"No rows found for run ID `{st.session_state.run_id}`. "
                            "The table might not have been copied yet, or the run ID doesn't exist."
                        )

                    if before_df is not None and len(before_df) > 0:
                        st.markdown(f"**Table:** `{entry['table']}`")
                        tab_before, tab_after = st.tabs(["Before (Current Data)", "After (Projected)"])
                        with tab_before:
                            st.dataframe(before_df, use_container_width=True)
                        with tab_after:
                            if after_df is not None:
                                if changed:
                                    st.dataframe(_style_changed(after_df, changed), use_container_width=True)
                                    st.caption(
                                        f"Green = changed column{'s' if len(changed) != 1 else ''}: "
                                        + ", ".join(changed)
                                    )
                                else:
                                    st.dataframe(after_df, use_container_width=True)
                                    st.caption("No column changes detected (value might already match).")

                elif verb == "DELETE":
                    before_df = entry["before_df"]
                    if before_df is not None:
                        n = len(before_df)
                        st.markdown(f"**Table:** `{entry['table']}`")
                        st.warning(f"This will permanently DELETE {n} row{'s' if n != 1 else ''} from the table:")
                        st.dataframe(before_df, use_container_width=True)
                    else:
                        st.info("No rows found to delete (or preview failed).")

                else:
                    st.warning(f"Unexpected verb '{verb}' — only UPDATE and DELETE are supported.")

        # ── Confirmation gate ─────────────────────────────────────────────────
        if st.session_state.stage == "validated":
            st.divider()
            st.markdown("### Are these the changes you want to apply?")
            _rp_ok = all(
                st.session_state.get(f, "").strip()
                for f in ("rp_description", "rp_name", "rp_user")
            )
            if not _rp_ok:
                st.warning("Fill in all required Run Parameters above (description, name, user) before proceeding.")
            cc1, cc2 = st.columns(2)
            with cc1:
                if st.button(
                    "✅ Yes, these look correct — Proceed to Execute",
                    type="primary", use_container_width=True,
                    disabled=not _rp_ok,
                ):
                    st.session_state.stage = "confirmed"
                    st.session_state.preview_confirmed = True
                    st.rerun()
            with cc2:
                if st.button("❌ No, start over", use_container_width=True):
                    reset_flow()
                    st.rerun()

        elif st.session_state.stage == "confirmed":
            st.success("Preview confirmed — scroll down to execute.")

# ─────────────────────────────────────────────────────────────────────────────
# Step 4: Execute
# ─────────────────────────────────────────────────────────────────────────────
if st.session_state.stage == "confirmed":
    intent = st.session_state.intent
    mutations = intent.get("sql_mutations") or []
    run_params = {
        "description": st.session_state.get("rp_description", ""),
        "name": st.session_state.get("rp_name", ""),
        "user": st.session_state.get("rp_user", ""),
        "objective_function": st.session_state.get("rp_objective_function", "Maximize Bank Balance"),
        "timeout_seconds": st.session_state.get("rp_timeout_seconds", 600),
        "duration": st.session_state.get("rp_duration", 1351),
        "mip_gap": st.session_state.get("rp_mip_gap", 0.001),
        "start_period": st.session_state.get("rp_start_period", 461),
    }

    st.divider()
    st.subheader("Step 4: Execute")
    st.info(
        "These steps trigger live Fabric notebooks. "
        "Only press the buttons when you're ready to execute for real."
    )

    _active_run_id = st.session_state.run_id

    # Step 4.1
    form_mutations = _run_params_to_sql(run_params)
    all_mutations = form_mutations + mutations

    with st.expander("Step 4.1: Update Input (DE_NB_Update_Input)", expanded=True):
        total_stmts = len(all_mutations)
        st.markdown(
            f"Will run **DE_NB_Update_Input** with `run_id = {_active_run_id}` "
            f"and {total_stmts} SQL statement{'s' if total_stmts != 1 else ''} "
            f"({len(form_mutations)} from form + {len(mutations)} from NL intent)."
        )

        st.markdown("**Run Parameters → `input_parameters` (from form):**")
        for _sql in form_mutations:
            st.code(_sql, language="sql")

        if mutations:
            st.markdown("**NL intent mutations:**")
            for _i, _sql in enumerate(mutations, 1):
                st.code(_sql, language="sql")

        if st.button("▶ Run Step 4.1: Update Input", type="primary", key="btn_step6"):
            if not os.getenv("FABRIC_NOTEBOOK_UPDATE_INPUT_ID"):
                st.warning(
                    "FABRIC_NOTEBOOK_UPDATE_INPUT_ID not set in .env — "
                    "add the notebook item ID to enable this."
                )
            else:
                with st.spinner("Submitting to Fabric…"):
                    import base64
                    sql_b64 = base64.b64encode(";\n".join(all_mutations).encode()).decode()
                    ok, msg = run_fabric_notebook(
                        "FABRIC_NOTEBOOK_UPDATE_INPUT_ID",
                        {"run_id": _active_run_id, "sql_statements_b64": sql_b64},
                    )
                if ok:
                    st.success(f"Step 4.1 submitted. {msg}")
                else:
                    st.error(f"Step 4.1 failed: {msg}")

    # Step 4.2
    with st.expander("Step 4.2: Run Model (DE_NB_RunModel)", expanded=True):
        st.markdown(
            f"Will run **DE_NB_RunModel** with `run_id = {_active_run_id}`. "
            "The notebook reads all configuration directly from `input_parameters` "
            "(written by Step 4.1 above)."
        )

        if st.button("▶ Run Step 4.2: Run Model", type="primary", key="btn_step7"):
            if not os.getenv("FABRIC_NOTEBOOK_RUN_MODEL_ID"):
                st.warning(
                    "FABRIC_NOTEBOOK_RUN_MODEL_ID not set in .env — "
                    "add the notebook item ID to enable this."
                )
            else:
                with st.spinner("Submitting to Fabric…"):
                    ok, msg = run_fabric_notebook(
                        "FABRIC_NOTEBOOK_RUN_MODEL_ID",
                        {"run_id": _active_run_id},
                    )
                if ok:
                    st.success(f"Step 4.2 submitted. {msg}")
                else:
                    st.error(f"Step 4.2 failed: {msg}")

    # Step 4.3
    with st.expander("Step 4.3: Result Summary", expanded=True):
        st.json({
            "run_id": _active_run_id,
            "plain_english": intent.get("plain_english", ""),
            "sql_mutations_applied": len(mutations),
        })

    st.divider()
    if st.button("← Parse Another Command", type="primary"):
        reset_flow()
        st.rerun()

# ─────────────────────────────────────────────────────────────────────────────
# Session history
# ─────────────────────────────────────────────────────────────────────────────
if st.session_state.stage in ("validated", "confirmed") and st.session_state.intent:
    cmd = st.session_state.user_command
    last = st.session_state.history[-1]["prompt"] if st.session_state.history else None
    if cmd and cmd != last:
        st.session_state.history.append({"prompt": cmd, "response": st.session_state.intent})

if st.session_state.history:
    st.divider()
    with st.expander(
        f"📜 Session History ({len(st.session_state.history)} run{'s' if len(st.session_state.history) != 1 else ''})",
        expanded=False,
    ):
        for _i, _h in enumerate(reversed(st.session_state.history)):
            _idx = len(st.session_state.history) - _i
            st.markdown(f"**{_idx}.** `{_h['prompt']}`")
            with st.expander(f"Details #{_idx}", expanded=False):
                st.json(_h["response"])
