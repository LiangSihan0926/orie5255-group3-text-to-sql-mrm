"""Cross-tabulate archived caveat flags and supporting counts in saved pilot results."""
import argparse
import ast
import csv
import io
import sys
from collections import Counter
from itertools import permutations
from pathlib import Path

from verify_archive_diagnostics import is_candidate, parse_display, read_inputs, recheck_visible_keys


def caveat_keywords(repo):
    # Read the archived rule as data. The historical runner itself needs provider libraries.
    runner = repo / "archive/text2sql_bird/run_llm_agent.py"
    for node in ast.parse(runner.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "CAVEAT_KEYWORDS" for target in node.targets
        ):
            return ast.literal_eval(node.value)
    raise ValueError("Historical caveat rule missing")


def has_year_and_value(observed, reference, value_column):
    """Check that the same two visible columns match both years and their values."""
    targets = Counter((r[0], r[value_column]) for r in reference)
    return any(
        Counter((r[year], r[value]) for r in observed) == targets
        for year, value in permutations(range(len(observed[0])), 2)
    )


def audit(repo):
    rows, _, refs = read_inputs(repo)
    candidates = [r for r in rows if is_candidate(r)]
    recheck_visible_keys(candidates, refs)
    matches = [r for r in candidates if r["result_match"] == "True"]
    keywords = caveat_keywords(repo)
    flagged = Counter()
    for r in matches:
        terms = keywords.get(r["id"])
        observed = any(term in r["assumptions"].lower() for term in terms) if terms else None
        if r["caveat_ok"] != (str(observed) if terms else ""):
            raise ValueError(f"Caveat flag and saved assumptions disagree for {r['id']}")
        if observed is False:
            flagged[r["id"]] += 1

    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(["cohort", "case", "measure", "records_meeting_measure", "records_in_cohort",
                     "reference_values"])
    measured = "no archived caveat keyword in saved assumptions"
    cohort = "runtime-clean key match"
    writer.writerow([cohort, "all", measured, sum(flagged.values()), len(matches), ""])
    eligible = [r for r in matches if r["id"] in keywords]
    writer.writerow([cohort, "all with keyword rule", measured, sum(flagged.values()), len(eligible), ""])
    for cid in sorted(keywords, key=lambda k: (k[0], int(k[1:]))):
        writer.writerow([cohort, cid, measured, flagged[cid], sum(r["id"] == cid for r in matches), ""])

    for cid in ("E3", "T3", "T4"):
        observed = [parse_display(r["llm_result"]) for r in matches if r["id"] == cid]
        expected_value, loan_count = parse_display(refs[cid])[0]
        scalar = sum(display == [(expected_value,)] for display in observed)
        writer.writerow([cohort, cid, "saved result contains only the matching scalar",
                         scalar, len(observed), f"supporting loan count {loan_count}"])

    reference = parse_display(refs["T8"])
    t8_matches = [r for r in matches if r["id"] == "T8"]
    t8_partials = [r for r in rows if r["id"] == "T8" and r["action"] == "partial" and r["llm_result"]]
    for label, group in [(cohort, t8_matches), ("partial action with saved result", t8_partials)]:
        observed = [parse_display(r["llm_result"]) for r in group]
        for name, column in [("origination counts", 1), ("finished-loan counts", 2),
                             ("B share among finished loans", 3), ("B/D share among all originations", 4)]:
            shown = sum(has_year_and_value(display, reference, column) for display in observed)
            values = " / ".join(f"{r[0]}={r[column]}" for r in reference)
            writer.writerow([label, "T8", f"both years paired with {name}", shown, len(group), values])
    return output.getvalue()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--check", type=Path, help="Compare the recomputed table with this archived CSV")
    args = parser.parse_args()
    table = audit(args.repo.resolve())
    if args.check:
        if table.encode("utf-8") != args.check.read_bytes():
            raise SystemExit("Pilot disclosure evidence differs from recomputed values.")
        print("Pilot disclosure flags and supporting counts agree with the archived CSV.")
    else:
        sys.stdout.write(table)


if __name__ == "__main__":
    main()
