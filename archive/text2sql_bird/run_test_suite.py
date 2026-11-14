"""
Run the offline test suite against financial.sqlite (read-only).

  python run_test_suite.py            -> prints a report, writes test_suite_results.csv / .md

It also contains a minimal reference implementation of two guardrail nodes so the
adversarial cases can be demonstrated:
  N5  syntactic / statement-type validation  (sqlglot)
  N6  PII projection check                    (sqlglot)
plus the database-level control: a read-only SQLite connection (mode=ro).
"""
import csv, sqlite3, sys
from pathlib import Path

import sqlglot
from sqlglot import exp

from test_suite import CASES

HERE = Path(__file__).parent
DB = HERE / "financial.sqlite"
RESTRICTED = {("client", "birth_date"), ("trans", "account"), ("order", "account_to")}


def ro_conn():
    return sqlite3.connect(f"file:{DB}?mode=ro", uri=True)


def run(sql, conn):
    try:
        rows = conn.execute(sql).fetchall()
        return rows[:10]
    except Exception as e:  # noqa: BLE001
        return f"ERROR: {type(e).__name__}: {e}"


def fmt(rows):
    if isinstance(rows, str):
        return rows
    out = []
    for r in rows:
        out.append("(" + ", ".join(f"{v:.4f}" if isinstance(v, float) else str(v) for v in r) + ")")
    return " ".join(out)


# ---------------------------------------------------------------- guardrails
def n5_statement_check(sql):
    """Allow exactly one SELECT/WITH statement."""
    try:
        stmts = [s for s in sqlglot.parse(sql, read="sqlite") if s is not None]
    except Exception as e:  # noqa: BLE001
        return False, f"parse error: {e}"
    if len(stmts) != 1:
        return False, f"{len(stmts)} statements (only 1 allowed)"
    if not isinstance(stmts[0], (exp.Select, exp.Union)):
        return False, f"statement type {type(stmts[0]).__name__} not allowed"
    return True, "ok"


def n6_pii_check(sql):
    """Block restricted columns in the SELECT list (allowed inside WHERE/GROUP BY/expressions for banding)."""
    tree = sqlglot.parse_one(sql, read="sqlite")
    alias = {t.alias_or_name: t.name for t in tree.find_all(exp.Table)}
    for proj in tree.expressions:
        node = proj.this if isinstance(proj, exp.Alias) else proj
        if isinstance(node, exp.Column):  # bare column projected row-level
            table = alias.get(node.table, node.table)
            if (table, node.name) in RESTRICTED:
                return False, f"restricted column {table}.{node.name} projected"
    return True, "ok"


# ---------------------------------------------------------------- main
def main():
    conn = ro_conn()
    records = []
    for c in CASES:
        rec = dict(id=c["id"], category=c["category"], node=c["node"],
                   expected_behavior=c["expected_behavior"], question=c["question"])
        rec["gold_result"] = fmt(run(c["gold_sql"], conn)) if c.get("gold_sql") else ""
        rec["wrong_results"] = " || ".join(f"{k}: {fmt(run(s, conn))}" for k, s in c.get("wrong_sql", {}).items())
        rec["interpretations"] = " || ".join(f"{k}: {fmt(run(s, conn))}" for k, s in c.get("interpretations", {}).items())
        if c.get("attack_sql"):
            ok5, msg5 = n5_statement_check(c["attack_sql"])
            g = f"N5={'PASS' if ok5 else 'BLOCK'} ({msg5})"
            if ok5:
                ok6, msg6 = n6_pii_check(c["attack_sql"])
                g += f"; N6={'PASS' if ok6 else 'BLOCK'} ({msg6})"
            # defence in depth: what happens if the guardrails are bypassed?
            raw = conn.executescript if ";" in c["attack_sql"].strip().rstrip(";") else conn.execute
            try:
                raw(c["attack_sql"])
                g += "; read-only DB: EXECUTED"
            except Exception as e:  # noqa: BLE001
                g += f"; read-only DB: REJECTED ({e})"
            rec["guardrail_result"] = g
        else:
            rec["guardrail_result"] = ""
        records.append(rec)

    # integrity check: DB unchanged
    n_loans = conn.execute("SELECT COUNT(*) FROM loan").fetchone()[0]
    n_trans = conn.execute("SELECT COUNT(*) FROM trans").fetchone()[0]
    assert n_loans == 682 and n_trans == 1056320, "database was modified!"

    cols = list(records[0].keys())
    with open(HERE / "test_suite_results.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(records)
    for r in records:
        print(f"\n[{r['id']}] {r['category']}  ({r['node']}, expect {r['expected_behavior']})\n  Q: {r['question']}")
        for k in ("gold_result", "wrong_results", "interpretations", "guardrail_result"):
            if r[k]:
                print(f"  {k}: {r[k]}")
    print(f"\nDB integrity OK (loan={n_loans}, trans={n_trans}). Wrote test_suite_results.csv")


if __name__ == "__main__":
    sys.exit(main())
