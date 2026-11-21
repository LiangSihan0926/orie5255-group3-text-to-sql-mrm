"""Distinct borrowing-account owners and mean approved principal by origination year."""

from datetime import date

from . import reference, routine

OWNERS = 'distinct_loan_account_owners'
YEAR_MEAN = 'mean_approved_amount_by_year'
YEAR_PROFILE = 'mean_approved_amount_by_origination_year'
YEARS = tuple(range(1993, date.fromisoformat(reference.AS_OF).year + 1))
IDS = frozenset({OWNERS, YEAR_MEAN, YEAR_PROFILE})


def catalog(metric_type, currency):
    # An annual mean uses the same two integer operands as the annual total.
    year_total = routine.catalog(metric_type, currency)['approved_amount_by_year']
    columns = []
    for year in YEARS:
        window = f"date >= '{year}-01-01' AND date < '{year + 1}-01-01'"
        columns.extend([f"COUNT(*) FILTER (WHERE {window})",
                        f"COALESCE(SUM(amount) FILTER (WHERE {window}), 0)"])
    return {
        OWNERS: metric_type(
            'clients', 'Number of distinct clients recorded as owners of accounts with at least one loan.',
            'Each identified owner counts once across all borrowing accounts and loans. '
            'An authorized user without an OWNER relationship does not qualify.',
            """SELECT (SELECT COUNT(DISTINCT d.client_id)
                       FROM disp AS d WHERE d.type = 'OWNER'
                       AND d.account_id IN (SELECT account_id FROM loan)),
                      COUNT(DISTINCT account_id), COUNT(*) FROM loan""",
            frozenset({('disp', 'account_id'), ('disp', 'client_id'), ('disp', 'type'),
                       ('loan', 'account_id')})),
        YEAR_MEAN: metric_type(
            'source_units', 'Arithmetic mean of approved principal per loan originated in the selected calendar year.',
            'Each loan counts once at origination, regardless of repayment status. ' + year_total.caveat,
            year_total.sql, year_total.reads),
        YEAR_PROFILE: metric_type(
            'source_units', 'Mean approved principal per loan, grouped by calendar year of origination.',
            'Each loan counts once. Each reported year includes its loan count and approved-principal sum. '
            'Years without originations have no mean and are listed separately. ' + year_total.caveat,
            'SELECT ' + ', '.join(columns) + ' FROM loan', year_total.reads),
    }


def base_counts(con, metric_id, scope):
    if metric_id == YEAR_MEAN:
        return routine.base_counts(con, 'approved_amount_by_year', scope)
    if metric_id == YEAR_PROFILE:
        yearly = {year: [0, 0] for year in YEARS}
        for day, amount in con.execute('SELECT date, amount FROM loan'):
            year = date.fromisoformat(day).year
            if year in yearly:
                yearly[year][0] += 1
                yearly[year][1] += amount
        return tuple(value for pair in yearly.values() for value in pair)
    if metric_id != OWNERS:
        raise ValueError('Unknown owner or origination measure')

    borrowing = set()
    loan_count = 0
    for (account,) in con.execute('SELECT account_id FROM loan'):
        borrowing.add(account)
        loan_count += 1
    accounted = set()
    owners = set()
    for account, client, relationship in con.execute('SELECT account_id, client_id, type FROM disp'):
        if account in borrowing and relationship == 'OWNER':
            if client is None:
                raise ValueError('A borrowing account has an unidentified owner')
            accounted.add(account)
            owners.add(client)
    if accounted != borrowing:
        raise ValueError('A borrowing account lacks an identifiable OWNER relationship')
    return len(owners), len(borrowing), loan_count


def render(metric_id, observed, scope):
    if metric_id == OWNERS:
        owners, accounts, loans = observed
        return owners, {'borrowing_account_count': accounts, 'loan_count': loans}
    if metric_id == YEAR_PROFILE:
        profile = {}
        missing = []
        for year, count, principal in zip(YEARS, observed[::2], observed[1::2]):
            if count:
                profile[str(year)] = {'loan_count': count, 'approved_amount_sum': principal,
                                      'mean': principal / count}
            else:
                missing.append(year)
        if not profile:
            raise ValueError('No origination year has a defined mean')
        return profile, {'loan_count': sum(observed[::2]), 'approved_amount_sum': sum(observed[1::2]),
                         'first_year': YEARS[0], 'last_year': YEARS[-1],
                         'years_with_loans': len(profile), 'years_without_loans': missing}
    if metric_id != YEAR_MEAN:
        raise ValueError('Unknown owner or origination measure')
    count, total = observed
    if count == 0:
        raise ValueError('An origination year without loans has no mean')
    return total / count, {'loan_count': count, 'approved_amount_sum': total, 'origination_year': scope}
