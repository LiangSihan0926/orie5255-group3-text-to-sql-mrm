"""Exercise designed, standalone English resubmissions after the six known clarifications."""
import argparse
import csv
import io
import json
import sys
from datetime import date, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from verify_clarified_portfolio import reference_cases as portfolio_references
from validation import reference
from validation.challenge_runner import definition_cards, numeric_match
from validation.questions import answer_question
from validation.shadow import open_shadow
from validation.shadow_score import answer_has_disclosures


# Each question below goes through the public English route without the original
# wording, a previous reply, a case ID, an SQL query or a structured contract.
RESUBMISSIONS = [
    ("T6", "How many loans were scheduled to be active on 1996-12-31?", "scheduled_active_loans", None),
    ("T6", "How many loans were actually performing on 1996-12-31?", None, None),
    ("T7", "What was the average 1995 booking-district unemployment rate with equal weight per loan?",
     "district_unemployment_1995_by_loan_count", None),
    ("T7", "What was the average 1995 booking-district unemployment rate weighted by approved loan amount?",
     "district_unemployment_1995_by_approved_amount", None),
]
for vintage in (1994, 1997):
    RESUBMISSIONS.extend([
        ("T8", f"For {vintage} originations, what share of finished loans had status B at the snapshot?",
         "vintage_finished_unpaid_share", vintage),
        ("T8", f"For {vintage} originations, what share of all loans had status B or D at the snapshot?",
         "vintage_distressed_loan_share", vintage),
    ])
RESUBMISSIONS.extend([
    ("A1", "At the 1998-12-31 snapshot, which booking-branch region had the highest share of loans "
     "with status B or D, counting each loan once?", "booking_distressed_rank_by_count", None),
    ("A2", "How many distinct owners of accounts with an originated loan appear in the 1998-12-31 snapshot?",
     "distinct_loan_account_owners", None),
    ("A3", "What was the average approved loan amount in source units for loans originated in calendar year 1997?",
     "mean_approved_amount_by_year", 1997),
])


def reference_cases(compressed):
    with reference.snapshot(compressed) as con:
        cases = {(card["request"]["metric"], card["request"].get("vintage")):
                 (card["request"]["as_of"], card["expected"])
                 for card in definition_cards(con, reference.SNAPSHOT_SHA)}
        cases.update({key: (reference.AS_OF, expected) for key, expected in portfolio_references(con).items()})
        cutoff = date(1996, 12, 31)
        active = 0
        for day, months in con.execute("SELECT date, duration FROM loan"):
            start = date.fromisoformat(day)
            year, month = divmod(start.year * 12 + start.month - 1 + months, 12)
            maturity = date(year, month + 1, 1) + timedelta(days=start.day - 1)
            active += start <= cutoff < maturity
        cases["scheduled_active_loans", None] = (cutoff.isoformat(), {
            "value": active, "unit": "loans", "evidence": {"loan_count": active}})
    return cases


def equal_value(observed, expected):
    if isinstance(expected, dict):
        return isinstance(observed, dict) and observed.keys() == expected.keys() and all(
            equal_value(observed[key], target) for key, target in expected.items())
    return numeric_match(observed, expected)


def audit():
    compressed = REPO / "data/financial.sqlite.gz"
    expected = reference_cases(compressed)
    with (REPO / "archive/text2sql_bird/test_suite_results.csv").open(encoding="utf-8", newline="") as source:
        originals = {r["id"]: r["question"] for r in csv.DictReader(source)}
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(["original_case", "original_action", "standalone_question", "expected_action",
                     "observed_action", "expected_metric", "expected_value", "observed_value", "expected_unit",
                     "observed_unit", "expected_as_of", "observed_as_of", "expected_hold_reason",
                     "observed_hold_reason", "expected_support", "checks_passed"])
    with open_shadow(compressed) as session:
        first_actions = {}
        for cid in sorted({r[0] for r in RESUBMISSIONS}):
            initial = answer_question(session, originals[cid])
            if set(initial) != {"action", "question"} or initial["action"] != "clarify" or not initial["question"]:
                raise ValueError(f"Expected the original {cid} question to request clarification")
            first_actions[cid] = initial["action"]
        for cid, question, metric, vintage in RESUBMISSIONS:
            reply = answer_question(session, question)
            target_action = "answer" if metric else "hold"
            target_reason = "" if metric else "outside_question_catalog"
            cutoff, target = expected[metric, vintage] if metric else ("", {})
            if metric:
                matched = (reply["action"] == target_action and reply.get("metric") == metric
                           and answer_has_disclosures(reply) and reply.get("role") == "portfolio_analyst"
                           and reply.get("as_of") == cutoff and reply.get("unit") == target["unit"]
                           and equal_value(reply.get("value"), target["value"])
                           and reply.get("evidence") == target["evidence"])
            else:
                matched = (reply.get("action") == target_action and reply.get("reason") == target_reason
                           and set(reply) <= {"action", "reason", "explanation", "message"})
            if not matched:
                raise ValueError(f"English resubmission did not produce its specified outcome: {question}")
            writer.writerow([cid, first_actions[cid], question, target_action, reply["action"], metric,
                             json.dumps(target["value"], sort_keys=True) if metric else "",
                             json.dumps(reply["value"], sort_keys=True) if metric else "",
                             target.get("unit"), reply.get("unit"),
                             cutoff, reply.get("as_of"), target_reason, reply.get("reason"),
                             json.dumps(target["evidence"], sort_keys=True) if metric else "", matched])
    return output.getvalue()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", type=Path)
    args = parser.parse_args()
    table = audit()
    if args.check:
        if table.encode("utf-8") != args.check.read_bytes():
            raise SystemExit("English clarification paths differ from the archived CSV.")
        print(f"{len(RESUBMISSIONS)} standalone English resubmissions matched their specified outcomes.")
    else:
        sys.stdout.write(table)


if __name__ == "__main__":
    main()
