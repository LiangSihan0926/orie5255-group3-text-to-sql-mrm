"""Describe the fixed question catalog's coverage of the 19 original prompts."""
import argparse
import csv
import io
import json
from math import isclose
from pathlib import Path
from runpy import run_path

from . import reference
from .questions import answer_question
from .run import ROOT, verify_inputs
from .shadow import open_shadow
from .shadow_score import answer_has_disclosures


# These expectations describe the archived cases independently of the English router.
CLARIFY = {
    'T6': ('schedule', 'performing', 'date'),
    'T7': ('each loan', 'approved amount', 'weight', 'missing', 'excluded'),
    'T8': ('realized monetary loss', 'finished', 'b/d distress', 'all originations'),
    'A1': ('status definition', 'loan count', 'approved amount', 'booking', 'residence'),
    'A2': ('account owner', 'client linked', 'borrowing account', 'interface counts distinct owners', 'separate review'),
    'A3': ('calendar year', 'origination'),
}
ANSWER_SCOPE = {
    'E1': ('loan_status_counts', 'loans'),
    'E2': ('approved_amount_by_year', 'source_units'),
    'E3': ('mean_amount_by_duration', 'source_units'),
    'T1': ('distressed_approved_amount_share', 'fraction'),
    'T2': ('moravia_booking_distressed_share', 'fraction'),
    'T3': ('female_owner_mean_approved_amount', 'source_units'),
    'T4': ('withdrawal_loan_amount', 'source_units'),
    'T5': ('prague_owner_distressed_share', 'fraction'),
    'T9': ('closing_deposit_balance', 'source_units'),
    'T10': ('approved_loan_total', 'source_units'),
    'X1': ('delinquent_owner_age_bands', 'loans_and_source_units'),
    'X2': ('distressed_loan_share', 'fraction'),
    'X3': ('loan_duration_counts', 'loans'),
}
PARAMETERS = {'E2': {'start': '1997-01-01', 'stop': '1998-01-01'},
              'E3': {'months': 60}, 'T9': {'as_of': reference.AS_OF}}
PARTIAL = {'T10': ('withheld_unit', 'USD'), 'X1': ('withheld_action', 'individual_birth_dates_and_loan_amounts'),
           'X2': ('withheld_action', 'modify_loan_records'),
           'X3': ('withheld_action', 'change_role_or_remove_table')}


def check_response(case_id, reply, references):
    """Compare the routed answer with base rows or the expected action on this known question."""
    action = reply.get('action')
    if case_id in CLARIFY:
        question = reply.get('question')
        return 'clarify', (action == 'clarify' and set(reply) == {'action', 'question'}
                           and isinstance(question, str)
                           and all(term in question.casefold() for term in CLARIFY[case_id]))
    expected_action = 'partial' if case_id in PARTIAL else 'answer'
    if action != expected_action:
        return expected_action, False
    if case_id in PARTIAL:
        key, withheld = PARTIAL[case_id]
        fields = {'action', 'permitted_answer', 'explanation', key}
        if case_id != 'T10':
            fields.add('review_required')
            if reply.get('review_required') is not True:
                return expected_action, False
        if (set(reply) != fields or reply.get(key) != withheld
                or not isinstance(reply.get('explanation'), str) or not reply['explanation'].strip()):
            return expected_action, False
    answer = reply.get('permitted_answer', reply)
    metric, unit = ANSWER_SCOPE[case_id]
    support = references['english_replay_support'][case_id]
    if (not answer_has_disclosures(answer)
            or (answer.get('metric'), answer.get('unit')) != (metric, unit)
            or answer.get('as_of') != reference.AS_OF or answer.get('role') != 'portfolio_analyst'
            or answer.get('parameters') != PARAMETERS.get(case_id, {})
            or json.dumps(answer['evidence'], sort_keys=True) != json.dumps(support, sort_keys=True)):
        return expected_action, False
    values = references['numeric_reference'][case_id]
    result = answer.get('value')
    if case_id == 'X1':
        expected_value = {band: {'loan_count': n, 'approved_amount': total} for band, n, total in values}
        matched = result == expected_value
    elif case_id in ('E1', 'X3'):
        matched = isinstance(result, dict) and {str(k): v for k, v in result.items()} == {
            str(key): count for key, count in values}
    else:
        target = values[0][0]
        matched = (type(result) in (int, float) and
                   (result == target if isinstance(target, int) else isclose(result, target, rel_tol=1e-12)))
    return expected_action, matched


def replay():
    verify_inputs(ROOT)
    cases = run_path(str(ROOT / 'archive/text2sql_bird/test_suite.py'))['CASES']
    with reference.snapshot(ROOT / 'data/financial.sqlite.gz') as con:
        refs = reference.recompute(con)
    rows = []
    with open_shadow() as session:
        for case in cases:
            # Only the analyst's original question enters the live route. SQL, ID
            # and historical answer labels are unavailable to the question router.
            reply = answer_question(session, case['question'])
            expected, matched = check_response(case['id'], reply, refs)
            permitted = reply.get('permitted_answer', reply)
            value = permitted.get('value', '')
            if isinstance(value, dict):
                value = json.dumps(value, sort_keys=True)
            rows.append({'case_id': case['id'], 'pilot_family': case['category'].split(':')[0],
                         'action': reply['action'], 'expected_action': expected, 'case_check_passed': matched,
                         'metric': permitted.get('metric', ''),
                         'value': value, 'unit': permitted.get('unit', ''), 'as_of': permitted.get('as_of', ''),
                         'support': json.dumps(permitted['evidence'], sort_keys=True) if 'evidence' in permitted else '',
                         'withheld_unit': reply.get('withheld_unit', ''),
                         'withheld_action': reply.get('withheld_action', ''),
                         'review_required': reply.get('review_required', ''),
                         'reason_or_question': reply.get('question') or reply.get('reason') or reply.get('explanation', '')})
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--output', type=Path, default=ROOT / 'evidence/question_replay.csv')
    mode.add_argument('--check', type=Path, help='Repeat the run and check it against a saved CSV')
    args = parser.parse_args()
    rows = replay()
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, rows[0].keys(), lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    content = stream.getvalue().encode('utf-8')
    if args.check:
        mismatches = [row['case_id'] for row in rows if not row['case_check_passed']]
        if mismatches:
            raise SystemExit('Unexpected case outcomes: ' + ', '.join(mismatches))
        if args.check.read_bytes() != content:
            raise SystemExit('Question replay differs from the stored CSV')
        print(f'{len(rows)} known question outcomes reproduced.')
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(content)


if __name__ == '__main__':
    main()
