"""Execute approved, structured portfolio metrics against the pinned offline snapshot."""
import argparse
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from time import monotonic

from . import cohorts, owner_year, reference, regional, routine

CATALOG_VERSION = 'financial-aggregates-v3'
ROLE = 'portfolio_analyst'
MAX_SECONDS = 2.0
COMPRESSED = Path(__file__).resolve().parents[1] / 'data' / 'financial.sqlite.gz'
BEGIN = date(1993, 1, 1)
END = date.fromisoformat(reference.AS_OF)
SOURCE_CURRENCY = ('The provider column notes say USD, while the archived project dictionary says CZK. '
                   'Values are in source units. A USD conversion requires '
                   'an approved exchange rate and valuation date.')


@dataclass(frozen=True)
class Metric:
    unit: str
    definition: str
    caveat: str
    sql: str
    reads: frozenset[tuple[str, str]]


# Both the compiler and the renderer use this catalog. Ratios are formed from the
# two reconciled integer operands in Python to avoid SQLite integer division.
CATALOG = {
    'withdrawal_loan_amount': Metric(
        'source_units', 'Approved loan amount on accounts with a recorded card withdrawal.',
        'Any qualifying withdrawal in the snapshot establishes account eligibility, including a withdrawal after '
        'the loan approval date. Each loan contributes once. ' + routine.APPROVAL_DATE_NOTE + ' ' + SOURCE_CURRENCY,
        """SELECT COUNT(*), SUM(l.amount) FROM loan AS l
           WHERE l.account_id IN (SELECT t.account_id FROM trans AS t
                                  WHERE t.operation = 'VYBER KARTOU')""",
        frozenset({('loan', 'account_id'), ('loan', 'amount'),
                   ('trans', 'account_id'), ('trans', 'operation')})),
    'scheduled_active_loans': Metric(
        'loans', 'Loans originated on or before the cutoff with scheduled maturity after it.',
        'This is scheduled activity. The snapshot does not establish actual repayment status '
        'on a historical date. Maturity is exclusive and follows SQLite calendar-month arithmetic. '
        + routine.APPROVAL_DATE_NOTE,
        """SELECT COUNT(*) FROM loan WHERE date <= :as_of
           AND date(date, '+' || duration || ' months') > :as_of""",
        frozenset({('loan', 'date'), ('loan', 'duration')})),
    'approved_loan_total': Metric(
        'source_units', 'Total approved amount of all loans in the snapshot.',
        'This measures approved principal. Outstanding exposure is unavailable. ' + SOURCE_CURRENCY,
        'SELECT COUNT(*), SUM(amount) FROM loan',
        frozenset({('loan', 'amount')})),
    'distressed_loan_share': Metric(
        'fraction', 'Loans in status B or D divided by all loans.',
        'B/D is a snapshot distress proxy with one vote per loan. Monetary loss is unavailable.',
        """SELECT SUM(CASE WHEN status IN ('B','D') THEN 1 ELSE 0 END), COUNT(*) FROM loan""",
        frozenset({('loan', 'status')})),
    'distressed_approved_amount_share': Metric(
        'fraction', 'Approved amount of status B/D loans divided by all approved loan amount.',
        'The weight is approved principal in source units. The snapshot has no outstanding '
        'balance by loan or measured monetary loss.',
        """SELECT SUM(CASE WHEN status IN ('B','D') THEN amount ELSE 0 END),
                  SUM(amount) FROM loan""",
        frozenset({('loan', 'status'), ('loan', 'amount')})),
    'finished_unpaid_share': Metric(
        'fraction', 'Finished unpaid loans (B) divided by all finished loans (A/B).',
        'This is a count share for finished contracts. Different follow-up periods affect '
        'vintage comparisons and the data contain no realized monetary losses.',
        """SELECT SUM(CASE WHEN status = 'B' THEN 1 ELSE 0 END),
                  SUM(CASE WHEN status IN ('A','B') THEN 1 ELSE 0 END) FROM loan""",
        frozenset({('loan', 'status')})),
    'running_delinquent_share': Metric(
        'fraction', 'Running delinquent loans (D) divided by all running loans (C/D).',
        'This is a count-based snapshot delinquency proxy. It does not measure arrears in currency.',
        """SELECT SUM(CASE WHEN status = 'D' THEN 1 ELSE 0 END),
                  SUM(CASE WHEN status IN ('C','D') THEN 1 ELSE 0 END) FROM loan""",
        frozenset({('loan', 'status')})),
}


CATALOG.update(routine.catalog(Metric, SOURCE_CURRENCY))
CATALOG.update(cohorts.catalog(Metric, SOURCE_CURRENCY))
CATALOG.update(owner_year.catalog(Metric, SOURCE_CURRENCY))
CATALOG.update(regional.catalog(Metric))

UNEMPLOYMENT_METRICS = {
    'district_unemployment_1995_by_loan_count': ('1', 'one vote per loan'),
    'district_unemployment_1995_by_approved_amount': ('l.amount', 'approved amount per loan'),
}
for metric_id, (weight, weighting) in UNEMPLOYMENT_METRICS.items():
    reads = {('loan', 'account_id'), ('account', 'account_id'), ('account', 'district_id'),
             ('district', 'district_id'), ('district', 'A12')}
    if weight == 'l.amount':
        reads.add(('loan', 'amount'))
    CATALOG[metric_id] = Metric(
        'percent', f'Mean 1995 booking-district unemployment rate, weighted by {weighting}.',
        'The booking district is linked through the loan account. Loans without an observed '
        'A12 rate are excluded from the weighted mean and counted separately. The rate '
        'describes the district in 1995, rather than an individual borrower at origination.',
        f"""SELECT SUM(CASE WHEN d.A12 IS NOT NULL
                            THEN CAST(ROUND(100 * d.A12) AS INTEGER) * {weight} ELSE 0 END),
                   SUM(CASE WHEN d.A12 IS NOT NULL THEN {weight} ELSE 0 END),
                   COUNT(d.A12), COUNT(*) - COUNT(d.A12)
            FROM loan AS l JOIN account AS a ON a.account_id = l.account_id
            JOIN district AS d ON d.district_id = a.district_id""",
        frozenset(reads))

VINTAGE_METRICS = {
    'vintage_finished_unpaid_share': ("status = 'B'", "status IN ('A','B')",
                                      'Finished loans that were unpaid (B), among finished loans (A/B).'),
    'vintage_distressed_loan_share': ("status IN ('B','D')", '1',
                                     'Loans in distress (B/D), among all loans in the origination year.'),
}
for metric_id, (in_numerator, in_denominator, definition) in VINTAGE_METRICS.items():
    CATALOG[metric_id] = Metric(
        'fraction', definition, 'Status is observed at the snapshot date. Follow-up differs by '
        'origination year; these count-based proxies do not measure currency losses. ' + routine.APPROVAL_DATE_NOTE,
        f"""SELECT SUM(CASE WHEN {in_numerator} THEN 1 ELSE 0 END),
                   SUM(CASE WHEN {in_denominator} THEN 1 ELSE 0 END),
                   COUNT(*), SUM(CASE WHEN status IN ('A','B') THEN 1 ELSE 0 END)
            FROM loan WHERE date >= :start AND date < :stop""",
        frozenset({('loan', 'status'), ('loan', 'date')}))


@dataclass(frozen=True)
class _Session:
    connection: sqlite3.Connection
    seconds: float


def _deny(*_):
    return sqlite3.SQLITE_DENY


@contextmanager
def open_shadow(compressed=None, *, timeout_seconds=MAX_SECONDS):
    """Open a private, hash-checked copy. The host supplies the authenticated role."""
    if not 0 < timeout_seconds <= MAX_SECONDS:
        raise ValueError('Request deadline must be positive and at most two seconds')
    with reference.snapshot(COMPRESSED if compressed is None else Path(compressed)) as con:
        con.set_authorizer(_deny)
        yield _Session(con, timeout_seconds)


def hold(reason, message):
    return {'action': 'hold', 'reason': reason, 'message': message}


def _authorizer(metric):
    tables = {table for table, column in metric.reads}

    def authorize(op, arg1, arg2, database, trigger):
        if trigger is not None:
            return sqlite3.SQLITE_DENY
        if op == sqlite3.SQLITE_SELECT:
            return sqlite3.SQLITE_OK
        if op == sqlite3.SQLITE_FUNCTION and arg2 in ('count', 'sum', 'date', 'round', 'coalesce', 'max'):
            return sqlite3.SQLITE_OK
        if op == sqlite3.SQLITE_FUNCTION and arg2 == 'substr' and ('client', 'birth_date') in metric.reads:
            return sqlite3.SQLITE_OK
        if op == sqlite3.SQLITE_FUNCTION and arg2 == 'row_number' and metric is CATALOG[cohorts.CLOSING_BALANCE]:
            return sqlite3.SQLITE_OK
        if op == sqlite3.SQLITE_READ and database in (None, 'main'):
            if (arg1, arg2) in metric.reads or (arg1 in tables and arg2 == ''):
                return sqlite3.SQLITE_OK
        return sqlite3.SQLITE_DENY

    return authorize


def _unemployment_counts(con, by_amount):
    # Rebuild each relationship from base keys and accumulate exact basis points. A12
    # has at most two decimal places on this snapshot. Keep the missing loans visible.
    districts = dict(con.execute('SELECT district_id, A12 FROM district'))
    account_districts = dict(con.execute('SELECT account_id, district_id FROM account'))
    select_loans = 'SELECT account_id, amount FROM loan' if by_amount else 'SELECT account_id, 1 FROM loan'
    weighted_sum = weight_sum = included = excluded = 0
    for account, weight in con.execute(select_loans):
        rate = districts[account_districts[account]]
        if rate is None:
            excluded += 1
            continue
        basis_points = Decimal(str(rate)) * 100
        if basis_points != basis_points.to_integral_value():
            raise ValueError('The catalog precision does not cover the observed rate')
        weighted_sum += int(basis_points) * weight
        weight_sum += weight
        included += 1
    return weighted_sum, weight_sum, included, excluded


def _base_counts(con, metric_id, cutoff, vintage):
    """Reconcile from base rows using a separate calculation and no generated SQL."""
    if metric_id in regional.IDS:
        return regional.base_counts(con, metric_id)
    if metric_id in owner_year.IDS:
        return owner_year.base_counts(con, metric_id, vintage)
    if metric_id in cohorts.IDS:
        return cohorts.base_counts(con, metric_id, cutoff)
    if metric_id in routine.IDS:
        return routine.base_counts(con, metric_id, vintage)
    if metric_id in UNEMPLOYMENT_METRICS:
        return _unemployment_counts(con, metric_id == 'district_unemployment_1995_by_approved_amount')
    if metric_id in VINTAGE_METRICS:
        states = [status for status, day in con.execute('SELECT status, date FROM loan')
                  if date.fromisoformat(day).year == vintage]
        finished = sum(status in reference.FINISHED for status in states)
        if metric_id == 'vintage_finished_unpaid_share':
            return states.count('B'), finished, len(states), finished
        return sum(status in reference.BAD for status in states), len(states), len(states), finished
    if metric_id == 'scheduled_active_loans':
        n = sum(date.fromisoformat(day) <= cutoff < reference.month_end(day, months)
                for day, months in con.execute('SELECT date, duration FROM loan'))
        return (n,)
    if metric_id == 'withdrawal_loan_amount':
        accounts = {account for account, event in con.execute('SELECT account_id, operation FROM trans')
                    if event == 'VYBER KARTOU'}
        amounts = [amount for account, amount in con.execute('SELECT account_id, amount FROM loan')
                   if account in accounts]
        return len(amounts), sum(amounts)
    if metric_id == 'approved_loan_total':
        amounts = [amount for (amount,) in con.execute('SELECT amount FROM loan')]
        return len(amounts), sum(amounts)
    if metric_id == 'distressed_approved_amount_share':
        rows = list(con.execute('SELECT status, amount FROM loan'))
        return sum(amount for status, amount in rows if status in reference.BAD), sum(amount for _, amount in rows)
    statuses = [status for (status,) in con.execute('SELECT status FROM loan')]
    if metric_id == 'distressed_loan_share':
        return sum(status in reference.BAD for status in statuses), len(statuses)
    if metric_id == 'finished_unpaid_share':
        return statuses.count('B'), sum(status in reference.FINISHED for status in statuses)
    if metric_id == 'running_delinquent_share':
        return statuses.count('D'), sum(status in ('C', 'D') for status in statuses)
    raise ValueError('Missing base-row reference')


def evaluate(session, request, *, role=ROLE):
    """Return a single proposed answer or a hold. Each call is one independent request."""
    if role != ROLE:
        return hold('unauthorized_role', 'The role has no access to this portfolio view.')
    fields = {'metric', 'as_of', 'snapshot_sha256', 'unit', 'vintage', 'duration_months', 'origination_year'}
    if not isinstance(request, dict) or set(request) - fields:
        return hold('unsupported_request', 'Submit one structured aggregate from the available catalog.')
    if not {'metric', 'as_of', 'snapshot_sha256'} <= request.keys():
        return hold('missing_contract', 'Specify the metric, cutoff date and expected database version.')
    if request['snapshot_sha256'] != reference.SNAPSHOT_SHA:
        return hold('snapshot_mismatch', 'The requested database version differs from the approved file.')
    metric_id = request['metric']
    if not isinstance(metric_id, str) or metric_id not in CATALOG:
        return hold('unknown_metric', 'Choose a defined portfolio measure with an explicit scope.')
    metric = CATALOG[metric_id]
    vintage = request.get('vintage')
    if metric_id in VINTAGE_METRICS:
        if type(vintage) is not int or vintage not in (1994, 1997):
            return hold('invalid_vintage', 'Choose an origination cohort of 1994 or 1997.')
    elif 'vintage' in request:
        return hold('unsupported_scope', 'This measure does not accept an origination-year filter.')
    for field, allowed_metrics, choices in (
        ('origination_year', ('approved_amount_by_year', owner_year.YEAR_MEAN), range(BEGIN.year, END.year + 1)),
        ('duration_months', ('mean_amount_by_duration',), (12, 24, 36, 48, 60)),
    ):
        if metric_id in allowed_metrics:
            value = request.get(field)
            if type(value) is not int or value not in choices:
                return hold('invalid_scope', 'Supply an available ' + field + ' for this metric.')
        elif field in request:
            return hold('unsupported_scope', 'This measure does not accept ' + field + '.')
    scope = request.get('origination_year', request.get('duration_months', vintage))
    if request.get('unit', metric.unit) != metric.unit:
        return hold('unsupported_unit', 'The requested unit requires an approved conversion or a different contract.')
    try:
        cutoff = date.fromisoformat(request['as_of'])
        if cutoff.isoformat() != request['as_of'] or not BEGIN <= cutoff <= END:
            raise ValueError
    except (TypeError, ValueError):
        return hold('invalid_cutoff', 'Use an available calendar date in YYYY-MM-DD format.')
    if metric_id != 'scheduled_active_loans' and cutoff != END:
        return hold('snapshot_only', 'This measure is approved only for the frozen snapshot date.')

    con = session.connection
    deadline = monotonic() + session.seconds
    params = {'as_of': cutoff.isoformat()} if metric_id in ('scheduled_active_loans', 'closing_deposit_balance') else {}
    if metric_id in VINTAGE_METRICS:
        params = {'start': f'{vintage}-01-01', 'stop': f'{vintage + 1}-01-01'}
    if metric_id in ('approved_amount_by_year', owner_year.YEAR_MEAN):
        params = {'start': f'{scope}-01-01', 'stop': f'{scope + 1}-01-01'}
    elif metric_id == 'mean_amount_by_duration':
        params = {'months': scope}
    con.set_authorizer(_authorizer(metric))
    con.set_progress_handler(lambda: int(monotonic() >= deadline), 1000)
    try:
        # Each template has one aggregate row. Reading one more detects excess output.
        rows = con.execute(metric.sql, params).fetchmany(2)
        if len(rows) != 1:
            return hold('output_grain', 'The query did not produce exactly one aggregate row.')
        observed = rows[0]
        expected = _base_counts(con, metric_id, cutoff, scope)
        if monotonic() >= deadline:
            return hold('timeout', 'The query or its reconciliation exceeded the time budget.')
        if observed != expected or any(type(value) is not int for value in observed):
            return hold('unreconciled', 'The aggregate and its supporting counts could not be verified.')
    except (ValueError, KeyError, TypeError):
        return hold('unreconciled', 'The frozen source does not satisfy the metric definition.')
    except sqlite3.Error:
        if monotonic() >= deadline:
            return hold('timeout', 'The query or its reconciliation exceeded the time budget.')
        return hold('execution_failed', 'The controlled read could not be completed.')
    finally:
        con.set_progress_handler(None, 0)
        con.set_authorizer(_deny)

    if metric_id in regional.IDS:
        try:
            value, evidence = regional.render(metric_id, observed)
        except ValueError:
            return hold('undefined_rate', 'No regional ranking with a positive denominator could be verified.')
    elif metric_id in owner_year.IDS:
        try:
            value, evidence = owner_year.render(metric_id, observed, scope)
        except ValueError:
            return hold('undefined_mean', 'No mean is defined for a population with no loans.')
    elif metric_id in cohorts.IDS:
        value, evidence = cohorts.render(metric_id, observed)
    elif metric_id in routine.IDS:
        try:
            value, evidence = routine.render(metric_id, observed, scope)
        except ValueError:
            return hold('undefined_mean', 'The requested population has no loans.')
    elif metric.unit == 'percent':
        weighted_sum, weight_sum, included, excluded = observed
        if weight_sum <= 0:
            return hold('undefined_rate', 'The linked loans have no observed rate with positive weight.')
        value = weighted_sum / (100 * weight_sum)
        evidence = {'included_loans': included, 'excluded_loans': excluded, 'weight_sum': weight_sum,
                    'weighted_rate_basis_points_sum': weighted_sum}
    elif metric.unit == 'fraction':
        numerator, denominator = observed[:2]
        if denominator <= 0 or not 0 <= numerator <= denominator:
            return hold('undefined_rate', 'A positive denominator and valid numerator are required.')
        value = numerator / denominator
        evidence = {'numerator': numerator, 'denominator': denominator}
        if metric_id in VINTAGE_METRICS:
            evidence.update(vintage=vintage, originated_loans=observed[2], finished_loans=observed[3])
    elif metric.unit == 'source_units':
        loan_count, value = observed
        evidence = {'loan_count': loan_count}
    else:
        value, = observed
        evidence = {'loan_count': value}
    return {
        'action': 'answer', 'metric': metric_id, 'definition': metric.definition,
        'value': value, 'unit': metric.unit, 'as_of': cutoff.isoformat(),
        'snapshot_sha256': reference.SNAPSHOT_SHA, 'snapshot_date': reference.AS_OF,
        'role': role, 'catalog_version': CATALOG_VERSION, 'evidence': evidence,
        'sql': metric.sql, 'parameters': params,
        'template_sha256': sha256(metric.sql.encode('utf-8')).hexdigest(), 'caveat': metric.caveat,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('metric', choices=sorted(CATALOG))
    parser.add_argument('--as-of', required=True, help='Requested financial cutoff, YYYY-MM-DD')
    parser.add_argument('--vintage', type=int, help='Origination year for a vintage-specific status proxy.')
    parser.add_argument('--origination-year', type=int, help='Origination year for a principal total or mean (1993 through 1998).')
    parser.add_argument('--duration-months', type=int, help='Contractual term for a mean.')
    parser.add_argument('--unit', help='Requested unit. Defaults to this measure’s native unit.')
    parser.add_argument('--snapshot-sha256', default=reference.SNAPSHOT_SHA,
                        help='Expected database identity. Defaults to the historical pilot snapshot.')
    args = parser.parse_args()
    request = {'metric': args.metric, 'as_of': args.as_of, 'snapshot_sha256': args.snapshot_sha256}
    if args.vintage is not None:
        request['vintage'] = args.vintage
    if args.origination_year is not None:
        request['origination_year'] = args.origination_year
    if args.duration_months is not None:
        request['duration_months'] = args.duration_months
    if args.unit is not None:
        request['unit'] = args.unit
    try:
        with open_shadow() as session:
            result = evaluate(session, request)
    except (OSError, EOFError, ValueError, sqlite3.Error):
        result = hold('source_unavailable', 'The frozen data source could not be verified and opened.')
    print(json.dumps(result, indent=2))
    return 0 if result['action'] == 'answer' else 2


if __name__ == '__main__':
    raise SystemExit(main())
