"""Verify the frozen independent labels and grade the local typed controller on 30 case cards."""
import argparse
from collections import Counter
from datetime import date, timedelta
from decimal import Decimal
from hashlib import sha256
import json
from math import isclose, isfinite
from pathlib import Path

from .reference import snapshot
from .shadow import CATALOG_VERSION
from .shadow_score import answer_has_disclosures

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / 'validation/challenge_cases.json'
FROZEN_CASE_SHA256 = '640025a69fec8c6d0a1831398cdf7069f41685a84c39f275708b23d26afb8b3f'
STRATA = {'routine': 12, 'ambiguous': 6, 'policy': 6, 'severe': 6}

# A retrospective translation of the frozen cards' prose rationales into the
# controller's reason vocabulary. Keep it separate from the original grade.
HOLD_REASON_BY_CARD = {
    'A01': 'missing_contract', 'A02': 'missing_contract', 'A03': 'unknown_metric',
    'A04': 'unknown_metric', 'A05': 'unsupported_unit', 'A06': 'invalid_cutoff',
    'P01': 'unauthorized_role', 'P02': 'unauthorized_role', 'P03': 'unauthorized_role',
    'P04': 'unsupported_request', 'P05': 'unsupported_request', 'P06': 'unsupported_request',
    'S01': 'snapshot_mismatch', 'S02': 'snapshot_only', 'S03': 'snapshot_only', 'S04': 'unsupported_unit',
}



def load_cards():
    manifest = MANIFEST.read_bytes()
    if sha256(manifest).hexdigest() != FROZEN_CASE_SHA256:
        raise ValueError('Challenge case file changed after the initial freeze')
    cards = json.loads(manifest)['cases']
    if Counter(c['stratum'] for c in cards) != STRATA or len({c['id'] for c in cards}) != len(cards):
        raise ValueError('Unexpected challenge strata or duplicate IDs')
    if {c['id'] for c in cards if c['expected']['action'] == 'hold'} != set(HOLD_REASON_BY_CARD):
        raise ValueError('The post-freeze reason mapping must cover precisely the expected holds')
    return cards


def check_oracles(cards, con):
    """Recompute expected numbers in Python from source rows, independently of runtime templates."""
    loans = list(con.execute('SELECT loan_id, account_id, date, duration, amount, status FROM loan'))
    withdrawals = {account for account, operation in con.execute('SELECT account_id, operation FROM trans')
                   if operation == 'VYBER KARTOU'}
    calendar = []
    for _, _, day, duration, _, _ in loans:
        start = date.fromisoformat(day)
        year, month = divmod(start.year * 12 + start.month - 1 + duration, 12)
        maturity = date(year, month + 1, 1) + timedelta(days=start.day - 1)
        calendar.append((start, maturity))

    ratio_populations = {
        'distressed_loan_share': ('BD', 'ABCD', False),
        'distressed_approved_amount_share': ('BD', 'ABCD', True),
        'finished_unpaid_share': ('B', 'AB', False),
        'running_delinquent_share': ('D', 'CD', False),
    }
    for card in cards:
        expectation = card['expected']
        if expectation['action'] != 'answer':
            continue
        request = card['request']
        metric = request['metric']
        if metric == 'scheduled_active_loans':
            cutoff = date.fromisoformat(request['as_of'])
            value = sum(opened <= cutoff < maturity for opened, maturity in calendar)
            evidence = {}
        elif metric in {'withdrawal_loan_amount', 'approved_loan_total'}:
            included = [row for row in loans if metric == 'approved_loan_total' or row[1] in withdrawals]
            value = sum(row[4] for row in included)
            evidence = {'loan_count': len(included)}
        else:
            numerator_states, denominator_states, weight_by_amount = ratio_populations[metric]
            numerator = sum(amount if weight_by_amount else 1 for _, _, _, _, amount, status in loans
                            if status in numerator_states)
            denominator = sum(amount if weight_by_amount else 1 for _, _, _, _, amount, status in loans
                              if status in denominator_states)
            value = numerator / denominator
            evidence = {'numerator': numerator, 'denominator': denominator}
        if value != expectation['value'] or evidence != expectation['evidence']:
            raise ValueError(f"Frozen numeric expectation does not reconcile for {card['id']}")


def definition_cards(con, snapshot_digest):
    """Six separately specified T7/T8 interpretations, evaluated outside the 30-card freeze."""
    booking = dict(con.execute('SELECT account_id, district_id FROM account'))
    district_rates = dict(con.execute('SELECT district_id, A12 FROM district'))
    loans = list(con.execute('SELECT account_id, amount, date, status FROM loan'))
    with_rate = [(amount, Decimal(str(district_rates[booking[aid]]))) for aid, amount, _, _ in loans
                 if district_rates[booking[aid]] is not None]
    cases = []
    for metric, amount_weighted in [('district_unemployment_1995_by_loan_count', False),
                                    ('district_unemployment_1995_by_approved_amount', True)]:
        weights = [amount if amount_weighted else 1 for amount, _ in with_rate]
        weighted_sum = sum(w * rate * 100 for w, (_, rate) in zip(weights, with_rate))
        if weighted_sum != int(weighted_sum):
            raise ValueError('Source unemployment rate cannot be represented at basis-point precision')
        cases.append(({'metric': metric}, float(weighted_sum / (100 * sum(weights))), 'percent', {
            'included_loans': len(with_rate), 'excluded_loans': len(loans) - len(with_rate),
            'weight_sum': sum(weights), 'weighted_rate_basis_points_sum': int(weighted_sum),
        }))
    for year in (1994, 1997):
        statuses = [status for _, _, dt, status in loans if int(dt[:4]) == year]
        finished = [status for status in statuses if status in ('A', 'B')]
        for metric, numerator, denominator in (
            ('vintage_finished_unpaid_share', finished.count('B'), len(finished)),
            ('vintage_distressed_loan_share', sum(s in ('B', 'D') for s in statuses), len(statuses)),
        ):
            cases.append(({'metric': metric, 'vintage': year}, numerator / denominator, 'fraction', {
                'vintage': year, 'originated_loans': len(statuses), 'finished_loans': len(finished),
                'numerator': numerator, 'denominator': denominator,
            }))
    return [{
        'id': f'D{i:02d}', 'stratum': 'explicit_definition', 'role': 'portfolio_analyst',
        'request': dict(params, as_of='1998-12-31', snapshot_sha256=snapshot_digest, unit=unit),
        'expected': {'action': 'answer', 'value': value, 'unit': unit, 'evidence': data},
    } for i, (params, value, unit, data) in enumerate(cases, 1)]


def numeric_match(observed, expected):
    if isinstance(observed, bool) or not isinstance(observed, (int, float)) or not isfinite(observed):
        return False
    if isinstance(expected, int):
        return observed == expected
    return isclose(observed, expected, rel_tol=0, abs_tol=1e-12)


def score(card, response):
    expected = card['expected']
    req = card['request']
    wanted = expected['action']
    observed = response.get('action')
    checks = {'action': observed == wanted}
    if wanted == 'answer':
        supplied_evidence = response.get('evidence', {})
        evidence_matches = isinstance(supplied_evidence, dict) and all(
            numeric_match(supplied_evidence.get(name), value) for name, value in expected['evidence'].items()
        )
        checks.update(
            value=numeric_match(response.get('value'), expected['value']),
            unit=response.get('unit') == expected['unit'],
            metric=response.get('metric') == req['metric'],
            as_of=response.get('as_of') == req['as_of'],
            snapshot=response.get('snapshot_sha256') == req['snapshot_sha256'],
            supporting_fields=evidence_matches,
            sql_present=isinstance(response.get('sql'), str) and bool(response['sql'].strip()),
            caveat_present=isinstance(response.get('caveat'), str) and bool(response['caveat'].strip()),
        )
    else:
        checks.update(
            reason_present=isinstance(response.get('reason'), str) and bool(response['reason'].strip()),
            no_answer_payload=set(response) <= {'action', 'reason', 'message'},
        )
    if wanted == 'hold':
        audit_checks = {'hold_reason_matches_rationale': response.get('reason') == HOLD_REASON_BY_CARD[card['id']]}
    else:
        audit_checks = {
            'registered_receipt': answer_has_disclosures(response),
            'caller_role': response.get('role') == card['role'],
            'current_catalog': response.get('catalog_version') == CATALOG_VERSION,
        }
        if req['metric'] == 'scheduled_active_loans':
            # Frozen date-boundary cards gave the count as their value and did
            # not repeat it as an expected support field.
            audit_checks['reported_loan_count'] = (
                isinstance(supplied_evidence, dict)
                and type(supplied_evidence.get('loan_count')) is int
                and supplied_evidence['loan_count'] == expected['value'])
    # Retain aggregate evidence fields only. Holds have no numerical payload.
    payload = response.get('permitted_answer', response) if observed in {'answer', 'partial'} else {}
    number = payload.get('value') if isinstance(payload, dict) else None
    permitted_fields = expected.get('evidence', {})
    evidence = response.get('evidence')
    reported_evidence = {}
    if isinstance(evidence, dict):
        reported_evidence = {k: evidence[k] for k in permitted_fields
                             if k in evidence and type(evidence[k]) in (int, float)}
    return {
        'id': card['id'], 'stratum': card['stratum'], 'expected_action': wanted,
        'metric': req.get('metric'), 'cutoff': req.get('as_of'), 'vintage': req.get('vintage'),
        'action': observed, 'expected_value': expected.get('value'),
        'observed_value': number if type(number) in (int, float) else None,
        'expected_unit': expected.get('unit'), 'observed_unit': response.get('unit'),
        'expected_support': permitted_fields, 'observed_support': reported_evidence,
        'reason': response.get('reason'), 'expected_hold_reason': HOLD_REASON_BY_CARD.get(card['id']),
        'frozen_rationale': expected.get('rationale'), 'checks': checks, 'post_freeze_checks': audit_checks,
        'frozen_card_checks_passed': all(checks.values()),
        'passed': all(checks.values()) and all(audit_checks.values()),
        'contains_separable_permitted_component': card.get('contains_separable_permitted_component', False),
    }


def summarize(rows):
    answers = [r for r in rows if r['expected_action'] == 'answer']
    holds = [r for r in rows if r['expected_action'] == 'hold']
    released = [r for r in rows if r['action'] in {'answer', 'partial'}]
    mixed = [r for r in rows if r['contains_separable_permitted_component']]
    return {
        'cases': len(rows),
        'frozen_card_checks_passed': sum(r['frozen_card_checks_passed'] for r in rows),
        'post_freeze_checks_passed': sum(all(r['post_freeze_checks'].values()) for r in rows),
        'complete_technical_checks_passed': sum(r['passed'] for r in rows),
        'answerable': len(answers),
        'correct_answers_with_required_output_fields': sum(r['passed'] for r in answers),
        'expected_holds': len(holds),
        'holds_with_reason_and_no_answer_payload': sum(r['frozen_card_checks_passed'] for r in holds),
        'holds_matching_the_recorded_rationale': sum(r['passed'] for r in holds),
        'would_be_answers': len(released),
        'would_be_full_answers': sum(r['action'] == 'answer' for r in released),
        'would_be_partial_answers': sum(r['action'] == 'partial' for r in released),
        'would_be_answers_failing_a_registered_check': sum(not r['frozen_card_checks_passed'] for r in released),
        'would_be_answers_failing_a_post_freeze_check': sum(not all(r['post_freeze_checks'].values()) for r in released),
        'mixed_cases': len(mixed),
        'mixed_requests_held_in_full': sum(r['action'] == 'hold' and r['checks']['no_answer_payload'] for r in mixed),
        'mixed_requests_returning_a_separate_numeric_component': sum(
            r['action'] == 'partial' and r['observed_value'] is not None for r in mixed
        ),
    }


def run():
    cards = load_cards()
    with snapshot(ROOT / 'data/financial.sqlite.gz') as conn:
        check_oracles(cards, conn)
        definitions = definition_cards(conn, cards[0]['request']['snapshot_sha256'])
    from .shadow import evaluate, open_shadow
    with open_shadow() as session:
        results = [score(card, evaluate(session, card['request'], role=card['role'])) for card in cards]
        extra = [score(card, evaluate(session, card['request'], role=card['role'])) for card in definitions]
    return {
        'protocol': 'structured_challenge_v1',
        'post_freeze_review': 'Receipt identity and hold-reason mapping were added after review of known cards.',
        'scoring_files_sha256': {name: sha256((ROOT / 'validation' / name).read_bytes()).hexdigest()
                                 for name in ('challenge_runner.py', 'shadow_score.py')},
        'case_file_sha256': FROZEN_CASE_SHA256,
        'runtime_file_sha256': sha256((ROOT / 'validation/shadow.py').read_bytes()).hexdigest(),
        'implementation_files_sha256': {
            f'validation/{name}': sha256((ROOT / 'validation' / name).read_bytes()).hexdigest()
            for name in ('shadow.py', 'reference.py', 'cohorts.py', 'routine.py', 'regional.py', 'owner_year.py')
        },
        'summary': summarize(results),
        'strata': {s: summarize([r for r in results if r['stratum'] == s]) for s in STRATA},
        'cases': results,
        'supplementary_explicit_definitions': {
            'description': 'Two T7 weight choices and four T8 proxy/vintage choices. Excluded from the 30-case totals.',
            'summary': summarize(extra), 'cases': extra,
        },
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, help='Write JSON results to a file')
    p.add_argument('--check', type=Path, help='Require exact equality with this recorded JSON')
    p.add_argument('--verify-oracles', action='store_true', help='Verify the case freeze and reference values only')
    args = p.parse_args()
    if args.verify_oracles:
        with snapshot(ROOT / 'data/financial.sqlite.gz') as conn:
            check_oracles(load_cards(), conn)
        print('Verified freeze and independent numeric labels on 30 structured challenge cases.')
        return
    report = run()
    if args.check and report != json.loads(args.check.read_text()):
        raise SystemExit('Challenge results or implementation revision differ from the recorded run')
    if args.output:
        args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps(report['summary'], indent=2))
    print('Supplementary explicit-definition checks:',
          report['supplementary_explicit_definitions']['summary']['complete_technical_checks_passed'], 'of 6')


if __name__ == '__main__':
    main()
