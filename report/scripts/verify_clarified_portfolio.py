"""Verify 20 explicitly scoped English requests against the pinned portfolio's base records."""
import argparse
import csv
from collections import defaultdict
from datetime import date
from fractions import Fraction
import io
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from validation import reference
from validation.questions import answer_question
from validation.shadow import CATALOG_VERSION, open_shadow
from validation.shadow_score import answer_has_disclosures

YEARS = range(1993, 1999)
OWNER_METRIC = 'distinct_loan_account_owners'
YEAR_METRIC = 'mean_approved_amount_by_year'
PROFILE_METRIC = 'mean_approved_amount_by_origination_year'
# These definitions and prompts specify the audit independently of the compiler.
PROXIES = {
    'distressed': ({'B', 'D'}, {'A', 'B', 'C', 'D'}, 'status B or D among all loans'),
    'unpaid_all': ({'B'}, {'A', 'B', 'C', 'D'}, 'status B among all loans'),
    'finished_unpaid': ({'B'}, {'A', 'B'}, 'status B among finished loans (A or B)'),
}
GEOGRAPHIES = {'booking': 'booking-branch', 'residence': 'account-owner residence'}
WEIGHTS = {'count': 'counting each loan once', 'amount': 'weighting each loan by its approved amount'}


def reference_cases(con):
    """Specify the 20 expected answers from individual loans, ownership links and district codes."""
    loans = list(con.execute('SELECT loan_id, account_id, date, amount, status FROM loan'))
    if len({loan[0] for loan in loans}) != len(loans):
        raise ValueError('Loan identities are not unique.')
    borrowing = {row[1] for row in loans}
    owners = defaultdict(list)
    for account, client, relationship in con.execute('SELECT account_id, client_id, type FROM disp'):
        if account in borrowing and relationship == 'OWNER':
            owners[account].append(client)
    if set(owners) != borrowing or any(len(people) != 1 for people in owners.values()):
        raise ValueError('Each borrowing account must have one attributable owner for the regional comparison.')
    accounts = dict(con.execute('SELECT account_id, district_id FROM account'))
    clients = dict(con.execute('SELECT client_id, district_id FROM client'))
    districts = dict(con.execute('SELECT district_id, A3 FROM district'))
    region_names = sorted(set(districts.values()))
    distinct_owners = {person for people in owners.values() for person in people}
    cases = {(OWNER_METRIC, None): {
        'unit': 'clients', 'value': len(distinct_owners),
        'evidence': {'borrowing_account_count': len(borrowing), 'loan_count': len(loans)}}}

    by_year = defaultdict(list)
    populations = {kind: defaultdict(list) for kind in GEOGRAPHIES}
    for _, account, day, amount, status in loans:
        by_year[date.fromisoformat(day).year].append(amount)
        populations['booking'][districts[accounts[account]]].append((status, amount))
        owner = owners[account][0]
        populations['residence'][districts[clients[owner]]].append((status, amount))

    profile = {}
    for year in YEARS:
        amounts = by_year[year]
        if not amounts:
            raise ValueError(f'No loan in the pinned audit year {year}.')
        total = sum(amounts)
        mean = float(Fraction(total, len(amounts)))
        cases[YEAR_METRIC, year] = {'unit': 'source_units', 'value': mean, 'evidence': {
            'origination_year': year, 'loan_count': len(amounts), 'approved_amount_sum': total}}
        profile[str(year)] = {'loan_count': len(amounts), 'approved_amount_sum': total, 'mean': mean}
    cases[PROFILE_METRIC, None] = {'unit': 'source_units', 'value': profile, 'evidence': {
        'loan_count': sum(row['loan_count'] for row in profile.values()),
        'approved_amount_sum': sum(row['approved_amount_sum'] for row in profile.values()),
        'first_year': YEARS[0], 'last_year': YEARS[-1], 'years_with_loans': len(profile), 'years_without_loans': []}}

    for geography, regions in populations.items():
        for proxy, (selected, eligible, _) in PROXIES.items():
            for weighting in WEIGHTS:
                metric = f'{geography}_{proxy}_rank_by_{weighting}'
                scores = {}
                eligible_loan_count = 0
                for region in region_names:
                    rows = [(status, amount) for status, amount in regions[region] if status in eligible]
                    eligible_loan_count += len(rows)
                    all_weights = [amount if weighting == 'amount' else 1 for status, amount in rows]
                    bad_weights = [w for (status, _), w in zip(rows, all_weights) if status in selected]
                    n, d = sum(bad_weights), sum(all_weights)
                    if d:
                        scores[region] = (n, d, Fraction(n, d))
                values = {}
                for region, (n, d, ratio) in scores.items():
                    rank = 1 + sum(candidate[2] > ratio for candidate in scores.values())
                    values[region] = {'rank': rank, 'numerator': n, 'denominator': d, 'rate': float(ratio)}
                cases[metric, None] = {'unit': 'regional_rate_ranking', 'value': values, 'evidence': {
                    'region_count': len(region_names), 'regions_ranked': len(scores),
                    'regions_without_denominator': len(region_names) - len(scores),
                    'loan_count': len(loans), 'eligible_loan_count': eligible_loan_count,
                    'total_numerator': sum(v[0] for v in scores.values()),
                    'total_denominator': sum(v[1] for v in scores.values())}}
    return cases


def questions():
    for geography, location in GEOGRAPHIES.items():
        for proxy, (_, _, definition) in PROXIES.items():
            for weight, wording in WEIGHTS.items():
                metric = f'{geography}_{proxy}_rank_by_{weight}'
                q = f'At the 1998-12-31 snapshot, rank {location} regions by the share of {definition}, {wording}?'
                if metric == 'booking_distressed_rank_by_count':
                    q = ('At the 1998-12-31 snapshot, which booking-branch region had the highest share '
                         'of loans with status B or D, counting each loan once?')
                yield (metric, None), q
    yield (OWNER_METRIC, None), 'How many distinct owners of accounts with an originated loan appear in the 1998-12-31 snapshot?'
    for year in YEARS:
        yield (YEAR_METRIC, year), f'What was the average approved loan amount in source units for loans originated in calendar year {year}?'
    yield (PROFILE_METRIC, None), 'Show the average approved loan amount by origination year in source units?'


def displayed_rows(metric, year, answer):
    value, support = answer['value'], answer['evidence']
    if answer['unit'] == 'regional_rate_ranking':
        for region in sorted(value, key=lambda name: (value[name]['rank'], name)):
            r = value[region]
            yield region, r['rank'], r['numerator'], r['denominator'], r['rate']
    elif metric == OWNER_METRIC:
        yield 'portfolio', '', '', '', value
    elif metric == YEAR_METRIC:
        yield year, '', support['approved_amount_sum'], support['loan_count'], value
    else:
        for group, row in sorted(value.items()):
            yield group, '', row['approved_amount_sum'], row['loan_count'], row['mean']


def audit():
    with reference.snapshot(ROOT / 'data/financial.sqlite.gz') as con:
        expected = reference_cases(con)
        borrowing = {a for a, in con.execute('SELECT account_id FROM loan')}
        linked = {c for a, c in con.execute('SELECT account_id, client_id FROM disp') if a in borrowing}
    output = io.StringIO(newline='')
    writer = csv.writer(output, lineterminator='\n')
    writer.writerow(['request', 'question', 'metric', 'action', 'unit', 'group', 'expected_rank', 'returned_rank',
                     'expected_numerator', 'returned_numerator', 'expected_denominator', 'returned_denominator',
                     'expected_value', 'returned_value', 'support', 'all_linked_clients_comparator',
                     'as_of', 'snapshot_sha256', 'catalog_version', 'template_sha256', 'verified'])
    prompts = list(questions())
    if len(prompts) != 20 or {key for key, _ in prompts} != set(expected):
        raise ValueError('The reference and English test cases must cover the same 20 requests.')
    row_count = 0
    with open_shadow() as session:
        for i, (key, prompt) in enumerate(prompts, 1):
            metric, year = key
            target = expected[key]
            actual = answer_question(session, prompt)
            comparison = {k: actual.get(k) for k in ('unit', 'value', 'evidence')}
            # JSON also distinguishes an integer operand from a Boolean or a rounded float.
            if (actual.get('action') != 'answer' or actual.get('metric') != metric
                    or actual.get('as_of') != reference.AS_OF or actual.get('catalog_version') != CATALOG_VERSION
                    or not answer_has_disclosures(actual)
                    or json.dumps(comparison, sort_keys=True) != json.dumps(target, sort_keys=True)):
                raise ValueError(f'English request {i} failed metric, provenance or base-row verification: {prompt}')
            for ref, observed in zip(displayed_rows(metric, year, target), displayed_rows(metric, year, actual)):
                group, rank, n, d, value = ref
                writer.writerow([i, prompt, metric, actual['action'], actual['unit'], group, rank, observed[1],
                                 n, observed[2], d, observed[3], value, observed[4],
                                 json.dumps(actual['evidence'], sort_keys=True, separators=(',', ':')),
                                 len(linked) if metric == OWNER_METRIC else '', actual['as_of'],
                                 actual['snapshot_sha256'], actual['catalog_version'], actual['template_sha256'], True])
                row_count += 1
    if row_count != 109:
        raise ValueError(f'Expected 109 regional, ownership and year records, found {row_count}.')
    return output.getvalue()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', type=Path)
    args = parser.parse_args()
    table = audit()
    if args.check:
        if args.check.read_bytes() != table.encode('utf-8'):
            raise SystemExit('The clarified portfolio audit differs from the archived CSV.')
        print('20 English requests and 109 groups agree with the independent base-record calculations.')
    else:
        sys.stdout.write(table)


if __name__ == '__main__':
    main()
