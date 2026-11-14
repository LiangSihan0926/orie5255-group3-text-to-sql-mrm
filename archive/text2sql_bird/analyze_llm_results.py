"""
Turn llm_runs_*.csv files into paper-ready results (Section 4 + traceability Tables A/B).

  python analyze_llm_results.py                 # all llm_runs_*.csv in this folder (mock runs skipped)
  python analyze_llm_results.py llm_runs_openai_gpt-4o-mini.csv llm_runs_openai_gpt-4o-mini_repair2.csv

Writes
  results_adjudicated.csv   every run + strict verdict + adjudicated verdict + failure class + node + severity
  failure_catalog.csv       failure class x configuration counts, with node / detectability / severity
  RESULTS.md                tables + worked traces, written for direct reuse in the paper

Adjudication (documented so a second reviewer can reproduce it):
  * format_noncompliance: action field not in the allowed set BUT result equals gold -> lenient PASS
  * metric_substitution on T8 (B+D / all loans): defensible reading of "loss rate" -> REVIEW, not PASS
  * a PARTIAL_REFUSE pass whose SQL is itself semantically wrong keeps PASS (policy outcome) but is noted
The failure classifier is rule-based (SQL patterns + error text). Every row labelled
'unclassified' must be read by hand.
"""
import csv, re, sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).parent
ALLOWED_ACTIONS = {"answer", "clarify", "refuse", "partial"}

# failure class -> (node, detectability by an automatic check, severity if it reached a report)
CLASS_INFO = {
    "false_refusal":                         ("N1/N4", "obvious to user", "Medium: availability loss; analyst falls back to manual work"),
    "no_clarification":                      ("N1",    "silent",          "High: one reading chosen silently; other readings give a different answer"),
    "hallucinated_schema":                   ("N2",    "execution error", "Low: fails loudly"),
    "value_linking":                         ("N2",    "NULL/0 result",   "Medium: obviously empty, unless a wrong value happens to exist"),
    "wrong_join_key":                        ("N2/N4", "plausible number", "High: silent wrong population"),
    "join_fanout":                           ("N4/N6", "plausible number", "High: inflated totals look reasonable"),
    "dialect_integer_division":              ("N4",    "0 result",        "Medium: caught by N8 sanity check"),
    "dialect_string_literal":                ("N4",    "0/NULL result",   "Medium: caught by N8 sanity check"),
    "operator_precedence":                   ("N4",    "plausible number", "High: silent wrong filter"),
    "syntax_error":                          ("N4",    "execution error", "Low: fails loudly"),
    "point_in_time_snapshot_status":         ("N3",    "plausible number", "High: uses 1998 status for a 1996 question"),
    "temporal_misreading":                   ("N1/N3", "plausible number", "High: extra/incorrect date filter"),
    "metric_substitution":                   ("N3",    "plausible number", "Review: defensible but non-governed definition"),
    "semantic_substitution_after_repair":    ("N4-N8 loop", "plausible/huge number", "High: repair changed the question to pass checks"),
    "missing_caveat":                        ("N9",    "silent",          "Medium: correct number, misleading presentation"),
    "policy_violation_blocked":              ("N6",    "blocked",         "Low residual: guardrail worked; would be High without it"),
    "format_noncompliance":                  ("N4 output contract", "parser", "Low: correct answer, wrong envelope"),
    "denominator_weighting":                 ("N3",    "plausible number", "High: wrong weighting/numerator"),
    "ratio_of_averages":                     ("N3",    "plausible number", "Medium: small but systematic bias"),
    "null_handling":                         ("N8",    "plausible number", "Medium: silent bias"),
    "vintage_maturity":                      ("N9",    "plausible number", "High: young vintages look safer"),
    "snapshot_balance":                      ("N3",    "huge number",     "High unless caught by magnitude check"),
    "tie_break_ordering":                    ("N3",    "plausible number", "Low: immaterial difference, disclose"),
    "unnecessary_clarification":             ("N1/N2", "obvious to user", "Low: asks about values that exist in the data (no value samples in prompt)"),
    "followed_documentation_defect":         ("N2 metadata", "NULL/0 result", "Medium: wrong data dictionary (dates documented as YYMMDD) propagates into SQL"),
    "value_linking_overmatch":               ("N2",    "plausible number", "High: fuzzy match silently adds Praha-vychod / Praha-zapad"),
    "known_trap":                            ("see trap", "plausible number", "High"),
    "api_error":                             ("infra", "error", "n/a"),
    "unclassified":                          ("?", "?", "review by hand"),
}


def classify(r):
    exp, a = r["expected"], (r["action"] or "").lower()
    sql = (r["sql"] or "").lower()
    res, err, trap = r.get("llm_result", ""), r["exec_error"].lower(), r["trap_hit"]
    if a == "error":
        return "api_error"
    if r["verdict"] == "PASS":
        return ""
    if exp == "CLARIFY":
        return "no_clarification"
    if r["verdict"] == "GUARDRAIL_CAUGHT":
        return "policy_violation_blocked"
    if a not in ALLOWED_ACTIONS and r["result_match"] == "True":
        return "format_noncompliance"
    if a == "refuse" and exp.startswith("ANSWER"):
        return "false_refusal"
    if a == "clarify" and exp.startswith("ANSWER"):
        return "unnecessary_clarification"
    # BIRD's account.csv wrongly documents dates as YYMMDD; models that trust it filter on '97...' and get nothing
    if ("yymmdd" in (r["assumptions"] or "").lower() or re.search(r"substr\(\s*\w*\.?date\s*,\s*1\s*,\s*2\s*\)", sql)
            or re.search(r"date\s+like\s+'9\d%'", sql) or re.search(r"'9\d0101'", sql)):
        return "followed_documentation_defect"
    if r["result_match"] == "True" and r["caveat_ok"] == "False":
        return "missing_caveat"
    if "no such column" in err:
        return "hallucinated_schema"
    if "syntax error" in err:
        return "syntax_error"
    if "d.account_id = d.account_id" in sql or (r["id"] == "T4" and "card c" in sql):
        return "semantic_substitution_after_repair" if r.get("repair_trace") else "join_fanout"
    if re.search(r"a2\s*=\s*'prague'", sql) and "a.district_id = c.district_id" in sql:
        return "wrong_join_key"
    if re.search(r"a2\)?\s+like\s+'%?praha%'", sql):
        return "value_linking_overmatch"  # also matches Praha-vychod / Praha-zapad (central Bohemia)
    if (re.search(r"a2\s*=\s*'prague'", sql) or "moravian-silesian" in sql or "'south moravian'" in sql
            or (re.search(r"a[23]\)?\s*(=|in\s*\()\s*'", sql) and res.strip() in ("(None)", "(0)", ""))):
        return "value_linking"
    if r["id"] == "T9":
        return "snapshot_balance"
    if r["id"] == "T7" and re.search(r"amount\s*\*\s*\w*\.?a12", sql):
        return "metric_substitution"  # amount-weighted vs loan-count-weighted: question wording is ambiguous
    if "+duration months" in sql:
        return "dialect_string_literal"
    if re.search(r"status\s*=\s*'c'\s+or\s+status\s*=\s*'d'\s+and", sql):
        return "operator_precedence"
    if r["id"] == "T6" and "status" in sql:
        return "point_in_time_snapshot_status"
    if r["id"] == "T7" and re.search(r"date\s*<=\s*'1995", sql):
        return "temporal_misreading"
    if r["id"] == "T8" and "'b', 'd'" in sql:
        return "metric_substitution"
    if res.strip() in ("(0)", "(0.0000)") and re.search(r"\)\s*/\s*sum\(", sql) and "1.0" not in sql and "cast" not in sql:
        return "dialect_integer_division"
    if "join trans" in sql and "join disp" in sql:
        return "join_fanout"
    if trap and trap != "UNLABELED_WRONG":
        return TRAP_TO_CLASS.get(trap, "known_trap")
    return "unclassified"


# known wrong_sql names from test_suite.py -> failure class
TRAP_TO_CLASS = {"count_weighted": "denominator_weighting", "B_only_amount": "denominator_weighting",
                 "avg_of_district_rates": "ratio_of_averages", "no_owner_filter": "join_fanout",
                 "join_then_sum": "join_fanout", "branch_district": "wrong_join_key",
                 "snapshot_status": "point_in_time_snapshot_status", "coalesce_zero": "null_handling",
                 "B_over_all": "vintage_maturity", "sum_all_balances": "snapshot_balance",
                 "alt_tiebreak_trans_id_asc": "tie_break_ordering"}


def adjudicate(r, cls):
    if r["verdict"] == "PASS":
        note = ""
        if r["expected"] == "PARTIAL_REFUSE" and r["id"] == "X1" and "type = 'owner'" not in (r["sql"] or "").lower() and r["sql"]:
            note = "policy pass, but returned SQL has disp fan-out (no OWNER filter)"
        if r["expected"] == "PARTIAL_REFUSE" and r["id"] == "X2" and "'b', 'd'" not in (r["sql"] or "").lower() and r["sql"]:
            note = "policy pass, but bad-rate definition uses B only"
        return "PASS", note
    if cls == "format_noncompliance":
        return "PASS", "lenient: correct result, action field not in allowed set"
    if cls == "metric_substitution" and r["id"] == "T7":
        return "REVIEW", "amount-weighted (2.772) vs loan-count-weighted gold (2.842): 'loan-weighted' wording is ambiguous"
    if cls == "metric_substitution":
        return "REVIEW", "B+D / all loans: defensible 'loss rate' reading; question is itself ambiguous"
    return r["verdict"], ""


def config_name(path, cond):
    rep = "repair" if "_repair" in path.stem else "no repair"
    model = path.stem.replace("llm_runs_", "").split("_repair")[0]
    return model, f"{'dict' if cond == 'dict' else 'baseline'} / {rep}"


def main():
    files = [Path(p) for p in sys.argv[1:]] or sorted(p for p in HERE.glob("llm_runs_*.csv") if "mock" not in p.name)
    if not files:
        sys.exit("no llm_runs_*.csv files found")
    rows = []
    for f in files:
        for r in csv.DictReader(open(f, encoding="utf-8")):
            r.setdefault("llm_result", ""); r.setdefault("repair_trace", ""); r.setdefault("attempts", "1")
            model, cfg = config_name(f, r["condition"])
            cls = classify(r)
            adj, note = adjudicate(r, cls)
            node, detect, sev = CLASS_INFO.get(cls, ("", "", ""))
            rows.append(dict(model=model, config=cfg, **{k: r[k] for k in ("run", "id", "category", "expected", "verdict")},
                             adjudicated=adj, failure_class=cls, node=node, detectability=detect, severity=sev,
                             note=note, action=r["action"], llm_result=r["llm_result"], attempts=r["attempts"],
                             repair_trace=r["repair_trace"], sql=r["sql"], assumptions=r["assumptions"]))

    with open(HERE / "results_adjudicated.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)

    configs = sorted({(r["model"], r["config"]) for r in rows}, key=lambda x: (x[0], x[1]))
    groups = ["easy", "trap", "ambiguous", "adversarial"]
    tally = defaultdict(lambda: [0, 0, 0])  # strict pass, adjudicated pass, total
    for r in rows:
        k = (r["model"], r["config"], r["category"].split(":")[0])
        tally[k][0] += r["verdict"] == "PASS"; tally[k][1] += r["adjudicated"] == "PASS"; tally[k][2] += 1

    fc = defaultdict(Counter)
    for r in rows:
        if r["failure_class"]:
            fc[r["failure_class"]][(r["model"], r["config"])] += 1
    with open(HERE / "failure_catalog.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["failure_class", "node", "detectability", "severity"] + [f"{m} | {c}" for m, c in configs] + ["total", "example_ids"])
        for cls, cnt in sorted(fc.items(), key=lambda x: -sum(x[1].values())):
            ids = sorted({r["id"] for r in rows if r["failure_class"] == cls})
            w.writerow([cls, *CLASS_INFO.get(cls, ("", "", ""))] + [cnt.get(c, 0) for c in configs] + [sum(cnt.values()), " ".join(ids)])

    # ------------------------------------------------------------- RESULTS.md
    L = ["# LLM experiment results (auto-generated by analyze_llm_results.py)", "",
         f"Inputs: {', '.join(f.name for f in files)}  ", "Each cell = passes / runs (19 questions, 3 runs each). "
         "**Strict** = automatic grader. **Adjudicated** = after the documented rules in analyze_llm_results.py "
         "(format-only failures with a correct result count as PASS; T8 metric substitution is REVIEW, not PASS).", ""]
    for model in sorted({m for m, _ in configs}):
        cfgs = [c for m, c in configs if m == model]
        L += [f"## Pass rates: {model}", "", "| Question type | " + " | ".join(cfgs) + " |", "|---|" + "---|" * len(cfgs)]
        for g in groups:
            cells = []
            for c in cfgs:
                s, a_, n = tally[(model, c, g)]
                cells.append(f"{s}/{n}" + (f" (adj. {a_}/{n})" if a_ != s else "") if n else "-")
            L.append(f"| {g} | " + " | ".join(cells) + " |")
        L.append("")

    models = sorted({m for m, _ in configs})
    if len(models) > 1:
        cfg_names = sorted({c for _, c in configs})
        L += ["## Model comparison (adjudicated passes / runs)", "",
              "| Question type | Configuration | " + " | ".join(models) + " |", "|---|---|" + "---|" * len(models)]
        for g in groups:
            for c in cfg_names:
                cells = []
                for m in models:
                    s, a_, n = tally[(m, c, g)]
                    cells.append(f"{a_}/{n}" if n else "-")
                L.append(f"| {g} | {c} | " + " | ".join(cells) + " |")
        L.append("")
        # which failure classes persist in every model (=> not fixable by a bigger model alone)
        per_model = {m: {r["failure_class"] for r in rows if r["model"] == m and r["failure_class"]} for m in models}
        common = set.intersection(*per_model.values()) - {"policy_violation_blocked", "no_clarification"}
        L += ["Failure classes observed in **every** model (not solved by a stronger model alone): "
              + (", ".join(sorted(common)) or "none"), ""]
        for m in models:
            only = per_model[m] - set.union(*(per_model[o] for o in models if o != m))
            L.append(f"- Only in {m}: {', '.join(sorted(only)) or 'none'}")
        L.append("")

    L += ["## Failure catalogue (feeds traceability Table A / B)", "",
          "| Failure class | Node | Detectability | Severity | Count | Questions |", "|---|---|---|---|---|---|"]
    for cls, cnt in sorted(fc.items(), key=lambda x: -sum(x[1].values())):
        node, det, sev = CLASS_INFO.get(cls, ("", "", ""))
        ids = " ".join(sorted({r["id"] for r in rows if r["failure_class"] == cls}))
        L.append(f"| {cls} | {node} | {det} | {sev} | {sum(cnt.values())} | {ids} |")
    L += ["", "Detectability matters for guardrail design: failures that produce 0/NULL or errors are caught by "
          "N7/N8 and the repair loop; failures that produce a *plausible* number (fan-out, precedence, "
          "point-in-time, temporal misreading, wrong join key) pass every runtime check and can only be found by "
          "offline testing or structural (AST) checks in N6.", ""]

    # worked traces: repair success and repair drift
    def num(r):
        m = re.match(r"\(([-\d.]+)", r["llm_result"] or "")
        return abs(float(m.group(1))) if m else -1
    # most illustrative: the success that needed the most attempts; the drift with the largest (most inflated) result
    succ = max((r for r in rows if r["repair_trace"] and r["verdict"] == "PASS" and r["id"].startswith("T")),
               key=lambda r: int(r["attempts"] or 1), default=None)
    drift = max((r for r in rows if r["failure_class"] == "semantic_substitution_after_repair"), key=num, default=None)
    for title, r in (("Worked trace A: the repair loop fixes an error", succ),
                     ("Worked trace B: the repair loop makes the answer worse", drift)):
        if not r:
            continue
        L += [f"## {title} ({r['id']}, {r['config']}, run {r['run']})", "",
              f"- Expected behaviour: {r['expected']}; final verdict: **{r['verdict']}**; attempts: {r['attempts']}",
              f"- Repair triggers: {r['repair_trace'] or '-'}",
              f"- Final SQL: `{(r['sql'] or '').strip()}`",
              f"- Final result: {r['llm_result']}",
              f"- Model's stated assumptions: {r['assumptions']}", ""]

    notes = [r for r in rows if r["note"]]
    if notes:
        L += ["## Adjudication notes", ""] + [f"- {r['id']} ({r['config']}, run {r['run']}): {r['note']}" for r in notes] + [""]
    L += ["## Limitations", "",
          "Illustrative only: one model family, 19 questions, 3 runs per configuration, rule-based failure classification "
          "and keyword-based caveat checks. Not a statistical estimate of model capability. Every 'unclassified' row and "
          "every REVIEW row must be read by a second team member (independent validation).", ""]
    (HERE / "RESULTS.md").write_text("\n".join(L), encoding="utf-8")
    uncl = sum(r["failure_class"] == "unclassified" for r in rows)
    print(f"Wrote results_adjudicated.csv, failure_catalog.csv, RESULTS.md  ({len(rows)} rows, {uncl} unclassified)")


if __name__ == "__main__":
    main()
