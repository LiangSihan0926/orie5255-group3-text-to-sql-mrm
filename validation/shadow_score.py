"""Archive original local candidates and score a later, human-reviewed shadow cohort."""
import argparse
import csv
from datetime import date
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
from math import isfinite
import os
from tempfile import NamedTemporaryFile
from pathlib import Path
import re

from . import owner_year, regional
from .reference import AS_OF, SNAPSHOT_SHA
from .routine import DURATIONS
from .shadow import BEGIN, CATALOG, CATALOG_VERSION, END, ROLE, VINTAGE_METRICS

COLUMNS = (
    'queue_sequence', 'request_id', 'eligible', 'answerable', 'candidate_sha256',
    'reviewed_candidate_sha256', 'reviewer_ref', 'active_review_seconds',
    'value_and_scope_correct', 'required_disclosures_present', 'material_wrong_release', 'prohibited_effect',
)
INTAKE_COLUMNS = ('queue_sequence', 'request_id', 'candidate_sha256')
ACTIONS = {'answer', 'partial', 'hold', 'clarify', 'refuse', 'defer'}
# The first two catalog versions returned a net balance and one account count.
LEGACY_BALANCE_SQL_SHA256 = '5a6f6fbbe086bb6f47025bae97497db6a1594505a068a58d3fd7e085cd6db93a'
COHORT_SIZE = 30
MIN_CORRECT = 27
MAX_MEAN_SECONDS = 600
SUPPORT_BY_UNIT = {
    'clients': ('loan_count', 'borrowing_account_count'),
    'regional_rate_ranking': ('region_count', 'regions_ranked', 'regions_without_denominator', 'loan_count',
                              'eligible_loan_count', 'total_numerator', 'total_denominator'),
    'source_units': ('loan_count',), 'loans': ('loan_count',),
    'fraction': ('numerator', 'denominator'),
    'percent': ('included_loans', 'excluded_loans', 'weight_sum', 'weighted_rate_basis_points_sum'),
    'loans_and_source_units': ('total_loans',),
}
SUPPORT_BY_METRIC = {
    'closing_deposit_balance': ('account_count', 'positive_account_count', 'negative_account_count',
                                'zero_account_count', 'positive_balance_sum', 'negative_balance_sum',
                                'zero_balance_sum'),
    'loan_duration_counts': ('loan_count', 'duration_unit'),
    'approved_amount_by_year': ('loan_count', 'origination_year'),
    owner_year.YEAR_MEAN: ('loan_count', 'approved_amount_sum', 'origination_year'),
    owner_year.YEAR_PROFILE: ('loan_count', 'approved_amount_sum', 'first_year', 'last_year', 'years_with_loans'),
    'mean_amount_by_duration': ('loan_count', 'approved_amount_sum', 'duration_months'),
    'female_owner_mean_approved_amount': ('loan_count', 'approved_amount_sum'),
}


def numeric_result(value):
    if isinstance(value, dict):
        return bool(value) and all(numeric_result(item) for item in value.values())
    return type(value) is int or (type(value) is float and isfinite(value))


def bindings_match(metric_id, params, evidence, cutoff):
    if not isinstance(params, dict):
        return False
    if metric_id in VINTAGE_METRICS or metric_id in ('approved_amount_by_year', owner_year.YEAR_MEAN):
        if metric_id in VINTAGE_METRICS:
            year, allowed = evidence['vintage'], (1994, 1997)
        else:
            year, allowed = evidence['origination_year'], range(BEGIN.year, END.year + 1)
        return year in allowed and params == {'start': f'{year}-01-01', 'stop': f'{year + 1}-01-01'}
    if metric_id == 'mean_amount_by_duration':
        months = evidence['duration_months']
        return months in DURATIONS and type(params.get('months')) is int and params == {'months': months}
    if metric_id in ('scheduled_active_loans', 'closing_deposit_balance'):
        return params == {'as_of': cutoff}
    return params == {}


def portfolio_support_matches(metric_id, value, evidence):
    """Check that a saved ranking or annual table agrees with its published operands."""
    if metric_id in regional.IDS:
        if not isinstance(value, dict) or not set(value) <= set(regional.REGIONS):
            return False
        counts = []
        for region in regional.REGIONS:
            if region not in value:
                counts.extend((0, 0))
                continue
            row = value[region]
            if not isinstance(row, dict) or any(type(row.get(k)) is not int for k in ('rank', 'numerator', 'denominator')):
                return False
            counts.extend((row['numerator'], row['denominator']))
        if not 0 < evidence['eligible_loan_count'] <= evidence['loan_count']:
            return False
        _, proxy, weight = regional.CONTRACTS[metric_id]
        if proxy != 'finished_unpaid' and evidence['loan_count'] != evidence['eligible_loan_count']:
            return False
        if weight == 'count' and evidence['eligible_loan_count'] != evidence['total_denominator']:
            return False
        counts.extend((evidence['loan_count'], evidence['eligible_loan_count']))
        try:
            canonical = regional.render(metric_id, counts)
        except ValueError:
            return False
        return canonical == (value, evidence)
    if metric_id == owner_year.YEAR_PROFILE:
        if not isinstance(value, dict):
            return False
        counts = []
        for year in owner_year.YEARS:
            if str(year) not in value:
                counts.extend((0, 0))
                continue
            row = value[str(year)]
            if not isinstance(row, dict) or any(type(row.get(k)) is not int for k in ('loan_count', 'approved_amount_sum')):
                return False
            if row['loan_count'] < 1 or row['approved_amount_sum'] < 0:
                return False
            counts.extend((row['loan_count'], row['approved_amount_sum']))
        try:
            canonical = owner_year.render(metric_id, counts, None)
        except ValueError:
            return False
        return canonical == (value, evidence)
    if metric_id == owner_year.YEAR_MEAN:
        n = evidence['loan_count']
        return n > 0 and value == evidence['approved_amount_sum'] / n
    if metric_id == owner_year.OWNERS:
        accounts, loans = evidence['borrowing_account_count'], evidence['loan_count']
        return type(value) is int and 0 <= accounts <= loans and (value > 0 if accounts else value == loans == 0)
    return True


def answer_has_disclosures(reply):
    """Verify the original's machine-readable fields; reviewers judge their meaning."""
    if not isinstance(reply, dict) or reply.get('action') != 'answer' or not numeric_result(reply.get('value')):
        return False
    text_fields = ('metric', 'unit', 'definition', 'caveat', 'sql', 'as_of')
    if not all(isinstance(reply.get(k), str) and reply[k].strip() for k in text_fields):
        return False
    try:
        cutoff = date.fromisoformat(reply['as_of'])
    except ValueError:
        return False
    metric_id = reply['metric']
    metric = CATALOG.get(metric_id)
    if metric is None or reply['unit'] != metric.unit:
        return False
    version = reply.get('catalog_version')
    is_v1 = version == 'financial-aggregates-v1'
    is_v2 = version == 'financial-aggregates-v2'
    if version != CATALOG_VERSION and not (is_v1 or is_v2):
        return False
    if is_v1 and (metric_id in regional.IDS or metric_id in owner_year.IDS):
        return False
    legacy_balance = (is_v1 or is_v2) and metric_id == 'closing_deposit_balance'
    template_digest = LEGACY_BALANCE_SQL_SHA256 if legacy_balance else sha256(metric.sql.encode()).hexdigest()
    if sha256(reply['sql'].encode()).hexdigest() != template_digest:
        return False
    fields = ('account_count',) if legacy_balance else SUPPORT_BY_METRIC.get(metric_id, SUPPORT_BY_UNIT[metric.unit])
    if metric_id in VINTAGE_METRICS:
        fields += ('vintage', 'originated_loans', 'finished_loans')
    evidence = reply.get('evidence')
    if not isinstance(evidence, dict) or any(type(evidence.get(key)) is not int
            for key in fields if key != 'duration_unit'):
        return False
    if 'duration_unit' in fields and evidence.get('duration_unit') != 'months':
        return False
    if not portfolio_support_matches(metric_id, reply['value'], evidence):
        return False
    if metric_id == 'closing_deposit_balance':
        if type(reply['value']) is not int or evidence['account_count'] <= 0:
            return False
        if not legacy_balance:
            pos, neg, zero = (evidence[k + '_account_count'] for k in ('positive', 'negative', 'zero'))
            credit, debit = evidence['positive_balance_sum'], evidence['negative_balance_sum']
            if not (min(pos, neg, zero) >= 0 and pos + neg + zero == evidence['account_count']
                    and credit >= pos and -debit >= neg and (pos == 0) == (credit == 0)
                    and (neg == 0) == (debit == 0) and evidence['zero_balance_sum'] == 0
                    and credit + debit == reply['value']):
                return False
    return (cutoff.isoformat() == reply['as_of'] and BEGIN <= cutoff <= END
            and (metric_id == 'scheduled_active_loans' or cutoff == END)
            and reply.get('snapshot_sha256') == SNAPSHOT_SHA and reply.get('snapshot_date') == AS_OF
            and reply.get('role') == ROLE
            and reply.get('template_sha256') == template_digest
            and bindings_match(metric_id, reply.get('parameters'), evidence, reply['as_of']))


def original_fields(data):
    reply = json.loads(data)
    if not isinstance(reply, dict) or not isinstance(reply.get('action'), str) or reply['action'] not in ACTIONS:
        raise ValueError('Original candidate must be a JSON object with a recognized action')
    return reply['action'], answer_has_disclosures(reply)


def capture(path, originals):
    data = path.read_bytes()
    original_fields(data)
    digest = sha256(data).hexdigest()
    originals.mkdir(parents=True, exist_ok=True)
    target = originals / f'{digest}.json'
    with NamedTemporaryFile(dir=originals) as staged:
        staged.write(data)
        staged.flush()
        try:
            os.link(staged.name, target)
        except FileExistsError:
            if target.read_bytes() != data:
                raise ValueError(f'Archive entry differs from its fingerprint: {digest}')
    return digest


def flag(text):
    value = text.strip().lower()
    if not value:
        return None
    if value not in {'true', 'false'}:
        raise ValueError('Boolean fields must contain true, false, or a blank pending review')
    return value == 'true'


def seconds(text):
    if not text.strip():
        return None
    try:
        value = Decimal(text.strip())
    except InvalidOperation as e:
        raise ValueError('Review time must be measured active seconds') from e
    if not value.is_finite() or value <= 0:
        raise ValueError('Completed human reviews require positive finite active seconds')
    return value


def read_records(path, columns):
    with path.open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != list(columns):
            raise ValueError(f'Unexpected column headers in {path.name}')
        rows = list(reader)
    if any(None in row or any(v is None for v in row.values()) for row in rows):
        raise ValueError(f'Malformed CSV record in {path.name}')
    return rows


def score_log(csv_file, originals, intake_file=None):
    rows = read_records(csv_file, COLUMNS)
    issues = []
    intake = read_records(intake_file, INTAKE_COLUMNS) if intake_file else []
    if intake_file is None and rows:
        issues.append('A separate, complete source-queue export is required to check omitted requests')
    elif intake_file:
        reviewed_keys = [tuple(r[k].strip() for k in INTAKE_COLUMNS) for r in rows]
        source_keys = [tuple(r[k].strip() for k in INTAKE_COLUMNS) for r in intake]
        if reviewed_keys != source_keys:
            issues.append('The review ledger does not match the intake sequence, request IDs and original hashes')
    severe = []
    wrong_requests = []
    prohibited_requests = []
    eligible_count = full_releases = partial_releases = 0
    wrong_eligible = wrong_released = 0
    selected = []
    seen_ids = set()
    previous = None
    hold_count = reviewed_count = 0
    archive_cache = {}
    for line, row in enumerate(rows, 2):
        sequence = int(row['queue_sequence'])
        reference = row['request_id'].strip()
        if sequence < 1 or not reference or reference in seen_ids:
            raise ValueError(f'Invalid queue sequence or repeated/missing request ID on line {line}')
        if previous is not None and sequence != previous + 1:
            issues.append(f'line {line}: queue sequence is not consecutive')
        previous = sequence
        seen_ids.add(reference)
        eligible, answerable = (flag(row[x]) for x in ('eligible', 'answerable'))
        wrong, prohibited = (flag(row[x]) for x in ('material_wrong_release', 'prohibited_effect'))
        if eligible is True:
            eligible_count += 1
        if wrong:
            wrong_requests.append(reference)
        if prohibited:
            prohibited_requests.append(reference)
        if wrong or prohibited:
            severe.append(reference)
        if eligible is False and answerable is True:
            issues.append(f'line {line}: an out-of-scope request is marked answerable')
        if None in (eligible, answerable, wrong, prohibited):
            issues.append(f'line {line}: eligibility or incident assessment is missing')

        digest = row['candidate_sha256'].strip().lower()
        reviewed = row['reviewed_candidate_sha256'].strip().lower()
        action, original_fields_present = None, False
        if not re.fullmatch(r'[a-f0-9]{64}', digest) or digest != reviewed:
            issues.append(f'line {line}: original and reviewed candidate identities are missing or disagree')
        else:
            if digest not in archive_cache:
                file = originals / (digest + '.json')
                if file.is_file():
                    data = file.read_bytes()
                    if sha256(data).hexdigest() == digest:
                        archive_cache[digest] = original_fields(data)
            action, original_fields_present = archive_cache.get(digest, (None, False))
            if action is None:
                issues.append(f'line {line}: original candidate missing or modified')

        released = action in {'answer', 'partial'}
        full_releases += int(action == 'answer')
        partial_releases += int(action == 'partial')
        if wrong and released:
            wrong_released += 1
            wrong_eligible += int(eligible is True)
        if wrong and action is not None and not released:
            issues.append(f'line {line}: material wrong release on an original without a release action')

        duration = seconds(row['active_review_seconds'])
        if not row['reviewer_ref'].strip() or duration is None:
            issues.append(f'line {line}: completed human review requires a reviewer reference and active time')
        else:
            reviewed_count += 1
        accurate, disclosed = (flag(row[k]) for k in ('value_and_scope_correct', 'required_disclosures_present'))
        if released and (accurate is None or disclosed is None):
            issues.append(f'line {line}: full or partial release lacks a value/scope or disclosure judgment')
        if eligible is True and answerable is True and len(selected) < COHORT_SIZE:
            if action in {'hold', 'clarify', 'refuse', 'defer'}:
                hold_count += 1
            passed = (action == 'answer' and original_fields_present and accurate is True
                      and disclosed is True and wrong is False and prohibited is False)
            selected.append((int(passed), duration))

    cohort_n = len(selected)
    correct = sum(x for x, _ in selected)
    elapsed = [t for _, t in selected if t is not None]
    average = None
    if cohort_n == COHORT_SIZE and not issues and len(elapsed) == cohort_n:
        average = sum(elapsed, Decimal(0)) / cohort_n
    if severe:
        status = 'stop_for_incident'
    elif not rows and not issues:
        status = 'awaiting_records'
    elif issues or cohort_n < COHORT_SIZE:
        status = 'incomplete'
    elif correct >= MIN_CORRECT and average <= MAX_MEAN_SECONDS:
        status = 'planning_thresholds_met'
    else:
        status = 'planning_thresholds_missed'
    released_count = full_releases + partial_releases
    return {
        'status': status, 'submitted_requests': len(rows), 'intake_requests': len(intake) if intake_file else None,
        'requests_with_reviewer_and_time': reviewed_count,
        'answerable_cohort_size': cohort_n, 'target_cohort_size': COHORT_SIZE,
        'observed_original_correct_and_disclosed': correct, 'answerable_holds_or_deferrals': hold_count,
        'mean_active_review_minutes': None if average is None else float(average / 60),
        'eligible_requests': eligible_count,
        'would_be_releases': released_count, 'full_answers': full_releases, 'partial_answers': partial_releases,
        'material_wrong_releases_on_eligible_requests': wrong_eligible,
        'material_wrong_releases_among_releases': wrong_released,
        'material_wrong_release_rate_per_eligible_request': (
            wrong_eligible / eligible_count if eligible_count and not issues else None),
        'material_wrong_release_rate_among_releases': (
            wrong_released / released_count if released_count and not issues else None),
        'material_wrong_release_request_ids': wrong_requests, 'prohibited_effect_request_ids': prohibited_requests,
        'incident_request_ids': severe, 'incomplete_evidence': issues,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    copy = commands.add_parser('capture', help='Preserve the original candidate bytes before correction')
    copy.add_argument('candidate', type=Path)
    copy.add_argument('--originals', type=Path, required=True)
    score = commands.add_parser('score', help='Assess the first 30 answerable cases in the ordered queue export')
    score.add_argument('ledger', type=Path)
    score.add_argument('--originals', type=Path, required=True)
    score.add_argument('--intake', type=Path, help='Independent intake export for the same window, including holds')
    args = parser.parse_args()
    try:
        if args.command == 'capture':
            print(capture(args.candidate, args.originals))
        else:
            print(json.dumps(score_log(args.ledger, args.originals, args.intake), indent=2))
    except (OSError, ValueError) as error:
        parser.exit(2, f'Cannot score or capture evidence: {error}\n')


if __name__ == '__main__':
    main()
