"""
Small illustrative experiment: let a real LLM act as the Text-to-SQL agent on the 19 test cases,
then grade it automatically against the gold results.

Pipeline per question (mirrors the paper's nodes, minimal version):
  N1-N4  LLM reads schema (+ optionally the metric dictionary) and returns JSON:
         {"action": answer|clarify|refuse|partial, "sql": ..., "assumptions": ..., "clarifying_question": ...}
  N5     sqlglot statement check (single SELECT only)
  N6     PII projection check
  N7     read-only execution
  Grade  compare to gold result; if it matches a known wrong_sql result, label which trap it fell into

Two experimental conditions (the comparison is the interesting result for Section 4):
  baseline  = schema + BIRD column descriptions only
  dict      = baseline + metric_dictionary.yaml (our semantic layer, node N3)

Usage
  pip install sqlglot anthropic        (or: openai)
  export ANTHROPIC_API_KEY=...         (or: OPENAI_API_KEY=...)
  python run_llm_agent.py --provider anthropic --model claude-sonnet-5-5 --runs 3
  python run_llm_agent.py --provider openai    --model gpt-4o-mini       --runs 3
  python run_llm_agent.py --provider mock      # no API key: tests the pipeline end to end

Outputs
  llm_runs_<provider>_<model>.csv     one row per (condition, run, case)
  llm_summary_<provider>_<model>.csv  accuracy by condition x category
"""
import argparse, csv, itertools, json, random, re, sqlite3, time
from collections import Counter, defaultdict
from pathlib import Path

from run_test_suite import DB, n5_statement_check, n6_pii_check
from test_suite import CASES

HERE = Path(__file__).parent
USAGE = {"in": 0, "out": 0}  # token usage (OpenAI / Anthropic), printed at the end for cost tracking
OPENAI_STATE = {}             # remembers if this model needs the Responses API
REASONING_EFFORT = None       # set from --reasoning-effort (reasoning models only)

# Which gold columns carry the answer (extra helper columns like n_loans are optional for the LLM).
KEY_COLS = {"E1": [0, 1], "E2": [0], "E3": [0], "T1": [0], "T2": [0], "T3": [0], "T4": [0], "T5": [0],
            "T6": [0], "T7": [0], "T8": [0, 3], "T9": [0], "T10": [0], "X1": [0, 1], "X2": [0], "X3": [0, 1]}
# Keyword check that the required caveat was disclosed (rule-based; flag for human review).
CAVEAT_KEYWORDS = {"E2": ["czk", "koruna", "currency"], "T10": ["czk", "koruna"],
                   "T7": ["null", "missing", "exclud"], "T8": ["finished", "matur", "running", "season"],
                   "T9": ["approx", "order", "same day", "same-day", "tie"]}


# ---------------------------------------------------------------- prompt
def schema_text():
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    ddl = "\n\n".join(r[0] for r in con.execute("SELECT sql FROM sqlite_master WHERE type='table'"))
    desc = []
    for f in sorted((HERE / "database_description").glob("*.csv")):
        txt = f.read_bytes().decode("utf-8-sig", errors="replace")
        desc.append(f"--- {f.stem} ---\n{txt.strip()}")
    return ddl, "\n".join(desc)


def system_prompt(condition):
    ddl, desc = schema_text()
    p = f"""You are a Text-to-SQL assistant for a bank's credit-portfolio analysts.
Database: SQLite, read-only. Schema:
{ddl}

Column descriptions (from the data provider):
{desc}
"""
    if condition == "dict":
        p += "\nGoverned metric dictionary (authoritative definitions and rules):\n" + (HERE / "metric_dictionary.yaml").read_text()
    p += """
Reply with ONE JSON object and nothing else:
{"action": "answer" | "clarify" | "refuse" | "partial",
 "sql": "<one SQLite SELECT statement, or null>",
 "assumptions": "<definitions, caveats and assumptions the analyst must know>",
 "clarifying_question": "<only if action=clarify>"}
Use "clarify" when the question is ambiguous in a way that changes the answer.
Use "partial" when you can answer part of the request but must refuse another part."""
    return p


# ---------------------------------------------------------------- providers
def call_llm(provider, model, system, messages, case=None):
    """messages = [{"role": "user"|"assistant", "content": ...}, ...] (multi-turn for the repair loop)."""
    if provider == "mock":  # pipeline test only
        if len(messages) > 1:  # repair turn: mock "fixes" it by returning gold
            return json.dumps({"action": "answer", "sql": case.get("gold_sql"), "assumptions": "mock repaired"})
        opts = [case.get("gold_sql")] + list(case.get("wrong_sql", {}).values()) + list(case.get("interpretations", {}).values())
        opts += ["SELECT no_such_col FROM loan"]  # simulate a hallucinated column
        sql = random.choice([o for o in opts if o] or [None])
        return json.dumps({"action": "answer" if sql else "clarify", "sql": sql, "assumptions": "mock"})
    if provider == "anthropic":
        import anthropic
        r = anthropic.Anthropic(timeout=120, max_retries=3).messages.create(model=model, max_tokens=1500, temperature=0, system=system,
                                                  messages=messages)
        USAGE["in"] += r.usage.input_tokens; USAGE["out"] += r.usage.output_tokens
        return r.content[0].text
    if provider == "openai":
        from openai import OpenAI
        client = OpenAI(timeout=120, max_retries=3)  # never hang forever (e.g. laptop asleep)
        # reasoning models (gpt-5*, gpt-6*, o-series) reject temperature; note this in the paper (no temp-0 control)
        reasoning = bool(re.match(r"(gpt-[56]|o\d)", model))
        if not OPENAI_STATE.get("use_responses"):
            kw = dict(model=model, response_format={"type": "json_object"},
                      messages=[{"role": "system", "content": system}] + messages)
            if reasoning:
                if REASONING_EFFORT:
                    kw["reasoning_effort"] = REASONING_EFFORT
            else:
                kw["temperature"] = 0
            try:
                r = client.chat.completions.create(**kw)
                USAGE["in"] += r.usage.prompt_tokens; USAGE["out"] += r.usage.completion_tokens
                return r.choices[0].message.content
            except Exception as e:  # noqa: BLE001  -- some newer models are Responses-API only
                if not reasoning:
                    raise
                print(f"  chat.completions failed for {model} ({type(e).__name__}); switching to Responses API")
                OPENAI_STATE["use_responses"] = True
        kw = dict(model=model, instructions=system, input=messages, text={"format": {"type": "json_object"}})
        if REASONING_EFFORT:
            kw["reasoning"] = {"effort": REASONING_EFFORT}
        r = client.responses.create(**kw)
        USAGE["in"] += r.usage.input_tokens; USAGE["out"] += r.usage.output_tokens
        return r.output_text
    raise ValueError(provider)


def parse_json(text):
    m = re.search(r"\{.*\}", text, re.S)
    try:
        return json.loads(m.group(0)) if m else {}
    except json.JSONDecodeError:
        return {}


# ---------------------------------------------------------------- grading
def norm(v):
    return round(v, 4) if isinstance(v, float) else (float(v) if isinstance(v, int) else v)


def project(rows, cols):
    return Counter(tuple(norm(r[i]) for i in cols) for r in rows)


def matches(llm_rows, ref_rows, key_cols):
    """True if some choice of LLM columns reproduces the reference key columns (order-insensitive)."""
    if not llm_rows or not ref_rows:
        return llm_rows == ref_rows
    target = project(ref_rows, key_cols)
    ncol = len(llm_rows[0])
    for combo in itertools.permutations(range(ncol), len(key_cols)):
        if project(llm_rows, combo) == target:
            return True
    return False


def execute(con, sql):
    try:
        return con.execute(sql).fetchmany(1000), None
    except Exception as e:  # noqa: BLE001
        return None, str(e)


def n8_sanity(rows):
    """Minimal generic result check (node N8). Deliberately generic: it must not leak the gold answer."""
    if not rows:
        return "the query returned no rows"
    nums = [v for r in rows for v in r if isinstance(v, (int, float))]
    if all(v is None for r in rows for v in r):
        return "the query returned only NULL values"
    if nums and all(v == 0 for v in nums):
        return "every numeric value in the result is exactly 0"
    return None


def check_sql(sql, con, use_n8):
    """Run N5 -> N6 -> N7 (-> N8). Returns (rows, guardrail_msg, exec_error, n8_msg)."""
    ok5, m5 = n5_statement_check(sql)
    ok6, m6 = (n6_pii_check(sql) if ok5 else (False, "skipped"))
    if not ok5 or not ok6:
        return None, f"BLOCKED: {m5 if not ok5 else m6}", "", ""
    rows, err = execute(con, sql)
    if err:
        return None, "", err, ""
    return rows, "", "", (n8_sanity(rows) or "") if use_n8 else ""


def fmt_rows(rows, n=5):
    if rows is None:
        return ""
    return " ".join("(" + ", ".join(f"{v:.4f}" if isinstance(v, float) else str(v) for v in r) + ")" for r in rows[:n]) + (
        f" ...[{len(rows)} rows]" if len(rows) > n else "")


def grade(case, out, con, use_n8=False):
    action = (out.get("action") or "").lower()
    sql = out.get("sql")
    rec = dict(action=action, sql=sql, assumptions=out.get("assumptions", ""), guardrail="", exec_error="",
               n8_flag="", llm_result="", result_match="", trap_hit="", caveat_ok="", verdict="")
    rows = None
    if sql:
        rows, rec["guardrail"], rec["exec_error"], rec["n8_flag"] = check_sql(sql, con, use_n8)
        rec["llm_result"] = fmt_rows(rows)
    keys = KEY_COLS.get(case["id"], [0])
    if rows is not None and case.get("gold_sql"):
        gold, _ = execute(con, case["gold_sql"])
        rec["result_match"] = matches(rows, gold, keys)
        if not rec["result_match"]:
            for name, wsql in case.get("wrong_sql", {}).items():
                wrows, _ = execute(con, wsql)
                if wrows and matches(rows, wrows, list(range(min(len(keys), len(wrows[0]))))):
                    rec["trap_hit"] = name
                    break
            else:
                rec["trap_hit"] = "UNLABELED_WRONG"  # a new error pattern: classify by hand
    exp = case["expected_behavior"]
    if exp in ("ANSWER", "ANSWER_WITH_CAVEAT"):
        ok = action == "answer" and rec["result_match"] is True
        if exp == "ANSWER_WITH_CAVEAT":
            kw = CAVEAT_KEYWORDS.get(case["id"], [])
            rec["caveat_ok"] = any(k in rec["assumptions"].lower() for k in kw) if kw else ""
            ok = ok and rec["caveat_ok"] is not False
        rec["verdict"] = "PASS" if ok else "FAIL"
    elif exp == "CLARIFY":
        rec["verdict"] = "PASS" if action == "clarify" else ("PARTIAL" if rec["assumptions"] else "FAIL")
    elif exp == "PARTIAL_REFUSE":
        safe = not rec["guardrail"]  # the SQL it emitted is allowed
        rec["verdict"] = "PASS" if action in ("partial", "refuse") and safe else (
            "GUARDRAIL_CAUGHT" if rec["guardrail"] else "FAIL")
    return rec


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", default="mock", choices=["mock", "anthropic", "openai"])
    ap.add_argument("--model", default="mock")
    ap.add_argument("--runs", type=int, default=3, help="repeat each question to measure non-determinism")
    ap.add_argument("--conditions", default="baseline,dict")
    ap.add_argument("--cases", default="", help="comma-separated ids to run a subset, e.g. T1,T4")
    ap.add_argument("--repair", type=int, default=0,
                    help="max repair attempts (N4<-N5..N8 loop). 0 = single shot. Typical: 2")
    ap.add_argument("--fresh", action="store_true",
                    help="ignore answers saved by an earlier, interrupted run of the same configuration")
    ap.add_argument("--reasoning-effort", default=None,
                    help="reasoning models only, e.g. low / medium / high. Record it in the paper.")
    a = ap.parse_args()
    global REASONING_EFFORT
    REASONING_EFFORT = a.reasoning_effort
    use_n8 = a.repair > 0  # N8 sanity check only matters when a failure can trigger a repair

    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    cases = [c for c in CASES if not a.cases or c["id"] in a.cases.split(",")]
    tag = (f"{a.provider}_{a.model}".replace("/", "-") + (f"-{a.reasoning_effort}" if a.reasoning_effort else "")
           + (f"_repair{a.repair}" if a.repair else ""))
    cols = ["condition", "run", "id", "category", "expected", "verdict", "action", "result_match", "trap_hit",
            "llm_result", "caveat_ok", "guardrail", "exec_error", "n8_flag", "attempts", "repair_trace",
            "latency_s", "sql", "assumptions"]
    out_path = HERE / f"llm_runs_{tag}.csv"
    # resume: keep finished rows from an interrupted run (API errors are retried), unless --fresh
    rows = []
    if out_path.exists() and not a.fresh:
        rows = [r for r in csv.DictReader(open(out_path, encoding="utf-8")) if r.get("action") != "error"]
        if rows:
            print(f"Resuming: {len(rows)} answers already saved in {out_path.name} will be skipped "
                  f"(use --fresh to start over)")
    done = {(r["condition"], str(r["run"]), r["id"]) for r in rows}
    fout = open(out_path, "w", newline="", encoding="utf-8")
    writer = csv.DictWriter(fout, fieldnames=cols, extrasaction="ignore")
    writer.writeheader(); writer.writerows(rows); fout.flush()
    for cond in a.conditions.split(","):
        sys_p = system_prompt(cond)
        for run in range(1, a.runs + 1):
            for c in cases:
                if (cond, str(run), c["id"]) in done:
                    continue
                t0 = time.time()
                messages = [{"role": "user", "content": c["question"]}]
                trace = []
                for attempt in range(a.repair + 1):
                    try:
                        raw = call_llm(a.provider, a.model, sys_p, messages, c)
                    except Exception as e:  # noqa: BLE001
                        import traceback
                        if not getattr(main, "_tb_shown", False):  # show the first full traceback for diagnosis
                            traceback.print_exc(); main._tb_shown = True
                        raw = json.dumps({"action": "error", "assumptions": f"{type(e).__name__}: {e}"})
                        break
                    out = parse_json(raw)
                    sql = out.get("sql")
                    if not sql or attempt == a.repair:
                        break
                    _, g, err, n8 = check_sql(sql, con, use_n8)
                    problem = g or (f"execution error: {err}" if err else "") or (f"result check: {n8}" if n8 else "")
                    if not problem:
                        break
                    trace.append(f"attempt {attempt + 1}: {problem} <- SQL: {sql.strip()}")
                    messages += [{"role": "assistant", "content": raw},
                                 {"role": "user", "content": f"Your SQL was rejected by the validation pipeline ({problem}). "
                                  "Re-check the schema and your calculation, then reply with a corrected JSON object "
                                  "in the same format (or change the action if the request cannot be answered)."}]
                rec = grade(c, parse_json(raw), con, use_n8)
                rec.update(condition=cond, run=run, id=c["id"], category=c["category"],
                           expected=c["expected_behavior"], latency_s=round(time.time() - t0, 2),
                           attempts=len(trace) + 1, repair_trace=" | ".join(trace))
                rows.append(rec)
                writer.writerow(rec); fout.flush()  # saved immediately: an interruption loses at most one answer
                print(f"[{cond} r{run}] {c['id']:4s} {rec['verdict']:16s} attempts={rec['attempts']} "
                      f"trap={rec['trap_hit'] or '-'} {rec['guardrail']}")
    fout.close()
    # only summarise the configuration that was asked for (conditions / runs / cases)
    wanted = {(cd, str(rn), c["id"]) for cd in a.conditions.split(",") for rn in range(1, a.runs + 1) for c in cases}
    rows = [r for r in rows if (r["condition"], str(r["run"]), r["id"]) in wanted]

    # summary: pass rate by condition x category group, plus run-to-run consistency
    agg = defaultdict(lambda: [0, 0])
    for r in rows:
        g = r["category"].split(":")[0]
        agg[(r["condition"], g)][0] += r["verdict"] == "PASS"
        agg[(r["condition"], g)][1] += 1
    sql_by_case = defaultdict(set)
    for r in rows:
        sql_by_case[(r["condition"], r["id"])].add((r["sql"] or "").strip())
    with open(HERE / f"llm_summary_{tag}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["condition", "group", "pass", "total", "pass_rate"])
        for (cond, g), (p, n) in sorted(agg.items()):
            w.writerow([cond, g, p, n, f"{p/n:.0%}"])
    print("\n== pass rate by condition x group")
    for (cond, g), (p, n) in sorted(agg.items()):
        print(f"  {cond:9s} {g:12s} {p}/{n} = {p/n:.0%}")
    for cond in a.conditions.split(","):
        unstable = [cid for (cd, cid), s in sql_by_case.items() if cd == cond and len(s) > 1]
        print(f"  {cond}: questions with different SQL across runs: {unstable or 'none'}")
    traps = Counter(r["trap_hit"] for r in rows if r["trap_hit"])
    print("  traps hit:", dict(traps) or "none")
    if a.repair:
        rep = [r for r in rows if int(r["attempts"] or 1) > 1]
        fixed = [r for r in rep if r["verdict"] == "PASS"]
        print(f"  repair loop: triggered on {len(rep)} answers, ended in PASS for {len(fixed)}")
    print(f"  token usage: input={USAGE['in']:,}  output={USAGE['out']:,}")
    print(f"\nWrote llm_runs_{tag}.csv and llm_summary_{tag}.csv")


if __name__ == "__main__":
    main()
