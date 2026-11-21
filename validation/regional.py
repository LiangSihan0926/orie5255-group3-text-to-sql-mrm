"""Rank the eight snapshot regions using explicit geography, status population and weight."""
from collections import defaultdict
from fractions import Fraction

# Fixed output columns keep a regional table within the one-row SQL result contract.
REGIONS = ('Prague', 'central Bohemia', 'east Bohemia', 'north Bohemia',
           'north Moravia', 'south Bohemia', 'south Moravia', 'west Bohemia')
GEOGRAPHIES = {'booking': 'booking-branch', 'residence': 'account-owner residence'}
# The archived A1 alternative counts B among all loans. B among finished loans is
# a different contract, even though the two definitions have the same numerator.
PROXIES = {
    'distressed': ("l.status IN ('B','D')", '1', 'status B or D among all loans'),
    'unpaid_all': ("l.status = 'B'", '1', 'status B among all loans'),
    'finished_unpaid': ("l.status = 'B'", "l.status IN ('A','B')", 'status B among finished loans (A or B)'),
}
WEIGHTS = {'count': 'counting each loan once', 'amount': 'weighting each loan by its approved amount'}
CONTRACTS = {
    f'{geography}_{proxy}_rank_by_{weight}': (geography, proxy, weight)
    for geography in GEOGRAPHIES for proxy in PROXIES for weight in WEIGHTS
}
IDS = frozenset(CONTRACTS)

QUESTION_FORMS = {}
for metric_id, (geography, proxy, weight) in CONTRACTS.items():
    region = GEOGRAPHIES[geography]
    measure = PROXIES[proxy][2]
    weighting = WEIGHTS[weight]
    QUESTION_FORMS[metric_id] = (f'At the 1998-12-31 snapshot, rank {region} regions by the share of '
                                 f'{measure}, {weighting}',)
QUESTION_FORMS['booking_distressed_rank_by_count'] += (
    'At the 1998-12-31 snapshot, which booking-branch region had the highest share of loans '
    'with status B or D, counting each loan once',)


def catalog(Metric):
    metrics = {}
    for metric_id, (geography, proxy, weight) in CONTRACTS.items():
        reads = {('loan', 'account_id'), ('loan', 'status'), ('district', 'district_id'), ('district', 'A3')}
        if geography == 'booking':
            joins = ('JOIN account AS a ON a.account_id = l.account_id '
                     'JOIN district AS d ON d.district_id = a.district_id')
            reads.update({('account', 'account_id'), ('account', 'district_id')})
        else:
            joins = ("JOIN disp AS p ON p.account_id = l.account_id AND p.type = 'OWNER' "
                     'JOIN client AS c ON c.client_id = p.client_id '
                     'JOIN district AS d ON d.district_id = c.district_id')
            reads.update({('disp', 'account_id'), ('disp', 'type'), ('disp', 'client_id'),
                          ('client', 'client_id'), ('client', 'district_id')})
        sql_weight = '1'
        if weight == 'amount':
            reads.add(('loan', 'amount'))
            sql_weight = 'l.amount'
        numerator, denominator, description = PROXIES[proxy]
        columns = []
        for region in REGIONS:
            for condition in (numerator, denominator):
                columns.append(f"COALESCE(SUM(CASE WHEN d.A3 = '{region}' AND ({condition}) "
                               f"THEN {sql_weight} ELSE 0 END), 0)")
        columns.extend(('COUNT(*)', f'COUNT(CASE WHEN {denominator} THEN 1 END)'))
        sql = 'SELECT ' + ',\n       '.join(columns) + '\nFROM loan AS l ' + joins
        metrics[metric_id] = Metric(
            'regional_rate_ranking',
            f'Regions by {GEOGRAPHIES[geography]}, ranked by the share of {description}, {WEIGHTS[weight]}.',
            'Statuses are observed at 1998-12-31. These fractions measure recorded status; realized losses '
            'are unavailable. Equal fractions share a rank. Regions with zero denominator have no rank. '
            'Amount weights use approved principal in source units.',
            sql, frozenset(reads))
    return metrics


def base_counts(con, metric_id):
    """Reconstruct every loan's region and count from base rows, independently of the SQL joins."""
    geography, proxy, weight = CONTRACTS[metric_id]
    districts = dict(con.execute('SELECT district_id, A3 FROM district'))
    if geography == 'booking':
        account_district = dict(con.execute('SELECT account_id, district_id FROM account'))
    else:
        clients = dict(con.execute('SELECT client_id, district_id FROM client'))
        owners = defaultdict(list)
        for account, client, role in con.execute('SELECT account_id, client_id, type FROM disp'):
            if role == 'OWNER':
                owners[account].append(client)
        # A loan must be attributable to exactly one owner. A missing/ambiguous
        # mapping on a borrowing account fails reconciliation when that loan is read.
        account_district = {account: clients[linked[0]] for account, linked in owners.items()
                            if len(linked) == 1}
    totals = {region: [0, 0] for region in REGIONS}
    loan_count = eligible_count = 0
    query = ('SELECT account_id, status, amount FROM loan' if weight == 'amount'
             else 'SELECT account_id, status, 1 FROM loan')
    for account, status, contribution in con.execute(query):
        region = districts[account_district[account]]
        if status not in ('A', 'B', 'C', 'D') or type(contribution) is not int or contribution < 0:
            raise ValueError('Unrecognized status or invalid approved amount.')
        numerator_and_denominator = totals[region]
        loan_count += 1
        if proxy == 'finished_unpaid' and status not in ('A', 'B'):
            continue
        eligible_count += 1
        numerator_and_denominator[1] += contribution
        if status == 'B' or (proxy == 'distressed' and status == 'D'):
            numerator_and_denominator[0] += contribution
    return (*[n for pair in totals.values() for n in pair], loan_count, eligible_count)


def render(metric_id, counts):
    """Competition ranks use exact rational comparisons, including ties displayed after JSON sorting."""
    regional_totals = dict(zip(REGIONS, zip(counts[0:-2:2], counts[1:-2:2])))
    rates = {}
    for region, (numerator, denominator) in regional_totals.items():
        if not 0 <= numerator <= denominator:
            raise ValueError('Invalid regional rate components.')
        if denominator:
            rates[region] = Fraction(numerator, denominator)
    if not rates:
        raise ValueError('No region has a positive denominator.')
    ranked = {}
    previous = None
    for position, region in enumerate(sorted(rates, key=lambda r: (-rates[r], r)), 1):
        if rates[region] != previous:
            rank = position
            previous = rates[region]
        numerator, denominator = regional_totals[region]
        ranked[region] = {'rank': rank, 'numerator': numerator, 'denominator': denominator,
                          'rate': float(rates[region])}
    return ranked, {
        'region_count': len(REGIONS), 'regions_ranked': len(ranked),
        'regions_without_denominator': len(REGIONS) - len(ranked),
        'loan_count': counts[-2], 'eligible_loan_count': counts[-1],
        'total_numerator': sum(pair[0] for pair in regional_totals.values()),
        'total_denominator': sum(pair[1] for pair in regional_totals.values()),
    }
