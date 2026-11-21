"""Fixed aggregate contracts for booking location, account owners and closing balances."""
from . import reference

MORAVIA = 'moravia_booking_distressed_share'
FEMALE_OWNER = 'female_owner_mean_approved_amount'
PRAGUE_OWNER = 'prague_owner_distressed_share'
CLOSING_BALANCE = 'closing_deposit_balance'
AGE_BANDS = 'delinquent_owner_age_bands'
IDS = frozenset({MORAVIA, FEMALE_OWNER, PRAGUE_OWNER, CLOSING_BALANCE, AGE_BANDS})


def catalog(metric_type, currency_caveat):
    links = {('loan', 'account_id'), ('disp', 'type'), ('disp', 'account_id'),
             ('disp', 'client_id'), ('client', 'client_id')}
    regions = {('district', 'district_id'), ('district', 'A3')}
    return {
        AGE_BANDS: metric_type('loans_and_source_units',
            'Count of running delinquent loans (status D) and total approved principal by account owner age band.',
            'Age is 1998 minus the owner’s birth year. Each status D loan contributes once. '
            'Approved principal does not measure arrears or outstanding debt. ' + currency_caveat,
            """SELECT COUNT(*) FILTER (WHERE age < 30), COALESCE(SUM(amount) FILTER (WHERE age < 30), 0),
                      COUNT(*) FILTER (WHERE age BETWEEN 30 AND 49),
                      COALESCE(SUM(amount) FILTER (WHERE age BETWEEN 30 AND 49), 0),
                      COUNT(*) FILTER (WHERE age >= 50), COALESCE(SUM(amount) FILTER (WHERE age >= 50), 0)
               FROM (SELECT 1998 - CAST(substr(c.birth_date, 1, 4) AS INTEGER) AS age, l.amount
                     FROM loan AS l JOIN disp AS d ON d.account_id = l.account_id AND d.type = 'OWNER'
                     JOIN client AS c ON c.client_id = d.client_id WHERE l.status = 'D')""",
            frozenset(links | {('loan', 'status'), ('loan', 'amount'), ('client', 'birth_date')})),
        MORAVIA: metric_type('fraction', 'B/D loans divided by all loans booked in north or south Moravia.',
            'The booking account selects the region. The two regions share one loan-count denominator. '
            'B/D is a status proxy, not a monetary loss.',
            """SELECT SUM(CASE WHEN l.status IN ('B','D') THEN 1 ELSE 0 END), COUNT(*)
               FROM loan AS l JOIN account AS a ON a.account_id = l.account_id
               JOIN district AS d ON d.district_id = a.district_id
               WHERE d.A3 IN ('north Moravia','south Moravia')""",
            frozenset(regions | {('loan', 'status'), ('loan', 'account_id'),
                                 ('account', 'account_id'), ('account', 'district_id')})),
        FEMALE_OWNER: metric_type('source_units', 'Mean approved amount per loan on accounts with a female owner.',
            'The borrower is the account OWNER. Other authorized users do not establish eligibility. '
            + currency_caveat,
            """SELECT COUNT(*), SUM(l.amount) FROM loan AS l
               JOIN disp AS d ON d.account_id = l.account_id AND d.type = 'OWNER'
               JOIN client AS c ON c.client_id = d.client_id WHERE c.gender = 'F'""",
            frozenset(links | {('loan', 'amount'), ('client', 'gender')})),
        PRAGUE_OWNER: metric_type('fraction', 'B/D loans divided by all loans whose account owner lives in Prague.',
            'Residence is the district of the account OWNER. An account booking branch or another '
            'authorized user can have a different address. B/D is a snapshot distress proxy.',
            """SELECT SUM(CASE WHEN l.status IN ('B','D') THEN 1 ELSE 0 END), COUNT(*) FROM loan AS l
               JOIN disp AS dp ON dp.account_id = l.account_id AND dp.type = 'OWNER'
               JOIN client AS c ON c.client_id = dp.client_id
               JOIN district AS d ON d.district_id = c.district_id WHERE d.A3 = 'Prague'""",
            frozenset(links | regions | {('loan', 'status'), ('client', 'district_id')})),
        CLOSING_BALANCE: metric_type('source_units',
            'Net signed balance across all accounts, using the last recorded balance at or before the cutoff.',
            'The net includes negative balances. Positive balances are shown separately. The snapshot '
            'does not establish a regulatory deposit-liability measure. The highest transaction ID '
            'breaks same-day ties because the actual posting order is unknown. ' + currency_caveat,
            # A transaction this month supersedes all earlier months. Only accounts
            # with no such transaction need their older history ranked.
            """SELECT COUNT(*), SUM(balance),
                      COUNT(*) FILTER (WHERE balance > 0), COUNT(*) FILTER (WHERE balance < 0),
                      COUNT(*) FILTER (WHERE balance = 0),
                      COALESCE(SUM(balance) FILTER (WHERE balance > 0), 0),
                      COALESCE(SUM(balance) FILTER (WHERE balance < 0), 0),
                      COALESCE(SUM(balance) FILTER (WHERE balance = 0), 0)
               FROM (
                   SELECT balance, ROW_NUMBER() OVER (
                       PARTITION BY account_id ORDER BY date DESC, trans_id DESC
                   ) AS closing_rank
                   FROM trans
                   WHERE date <= :as_of AND (
                       date >= date(:as_of, 'start of month') OR account_id IN (
                           SELECT account_id FROM account
                           EXCEPT SELECT account_id FROM trans
                                  WHERE date BETWEEN date(:as_of, 'start of month') AND :as_of
                       )
                   )
               ) WHERE closing_rank = 1""",
            frozenset({('trans', 'account_id'), ('trans', 'date'), ('trans', 'trans_id'),
                       ('trans', 'balance'), ('account', 'account_id')})),
    }


def _owners(con):
    owners = {}
    for account, client, role in con.execute('SELECT account_id, client_id, type FROM disp'):
        if role == 'OWNER':
            if account in owners:
                raise ValueError('Multiple owners on an account')
            owners[account] = client
    return owners


def _distress_counts(states):
    if not states:
        raise ValueError('An empty cohort has no rate')
    return sum(state in reference.BAD for state in states), len(states)


def _delinquent_owner_bands(con, cutoff):
    owners = _owners(con)
    loans = [(owners[account], amount) for account, amount in
             con.execute("SELECT account_id, amount FROM loan WHERE status = 'D'")]
    wanted = sorted({owner for owner, _ in loans})
    if not wanted:
        return 0, 0, 0, 0, 0, 0
    # Only the year leaves SQLite; restrict the read to owners of eligible loans.
    marks = ','.join('?' for _ in wanted)
    years = dict(con.execute('SELECT client_id, substr(birth_date, 1, 4) FROM client '
                             f'WHERE client_id IN ({marks})', wanted))
    counts = [0, 0, 0]
    amounts = [0, 0, 0]
    members = [set(), set(), set()]
    for owner, amount in loans:
        year = years[owner]
        if not isinstance(year, str) or len(year) != 4 or not year.isascii() or not year.isdigit():
            raise ValueError('An eligible owner lacks a valid four-digit birth year')
        if not 0 < int(year) <= cutoff.year or type(amount) is not int or amount < 0:
            raise ValueError('A loan or owner cannot be assigned to an age band')
        age = cutoff.year - int(year)
        band = 0 if age < 30 else 1 if age < 50 else 2
        counts[band] += 1
        amounts[band] += amount
        members[band].add(owner)
    if any(len(group) == 1 for group in members):
        raise ValueError('A band would reveal amounts for one owner')
    return counts[0], amounts[0], counts[1], amounts[1], counts[2], amounts[2]


def _closing_balance_counts(con, cutoff):
    accounts = {account for (account,) in con.execute('SELECT account_id FROM account')}
    latest = {}

    def track(rows):
        for account, day, transaction_id, balance in rows:
            # trans_id is a primary key, so day and transaction_id uniquely select a row.
            current = latest.get(account)
            if current is None or (day, transaction_id) > current[:2]:
                latest[account] = day, transaction_id, balance

    # Once an account has a row this month, older months cannot contain its last observation.
    # For every other account, read all earlier dates. The second pass uses bound base-row keys.
    month_start = cutoff.replace(day=1).isoformat()
    select = 'SELECT account_id, date, trans_id, balance FROM trans'
    track(con.execute(select + ' WHERE date BETWEEN ? AND ?', (month_start, cutoff.isoformat())))
    missing = sorted(accounts - latest.keys())
    for start in range(0, len(missing), 400):
        group = missing[start:start + 400]
        placeholders = ','.join('?' for _ in group)
        track(con.execute(select + f' WHERE date < ? AND account_id IN ({placeholders})',
                          (month_start, *group)))
    if latest.keys() != accounts:
        raise ValueError('An account lacks an observable balance at the cutoff')
    balances = [row[2] for row in latest.values()]
    positive = [balance for balance in balances if balance > 0]
    negative = [balance for balance in balances if balance < 0]
    return (len(balances), sum(balances), len(positive), len(negative), balances.count(0),
            sum(positive), sum(negative), 0)


def base_counts(con, metric_id, cutoff):
    if metric_id == AGE_BANDS:
        return _delinquent_owner_bands(con, cutoff)
    if metric_id == CLOSING_BALANCE:
        return _closing_balance_counts(con, cutoff)
    if metric_id == FEMALE_OWNER:
        owners = _owners(con)
        gender = dict(con.execute('SELECT client_id, gender FROM client'))
        amounts = [amount for account, amount in con.execute('SELECT account_id, amount FROM loan')
                   if gender[owners[account]] == 'F']
        if not amounts:
            raise ValueError('An empty cohort has no mean')
        return len(amounts), sum(amounts)

    district_region = dict(con.execute('SELECT district_id, A3 FROM district'))
    if metric_id == MORAVIA:
        bookings = dict(con.execute('SELECT account_id, district_id FROM account'))
        states = [state for account, state in con.execute('SELECT account_id, status FROM loan')
                  if district_region[bookings[account]] in ('north Moravia', 'south Moravia')]
        return _distress_counts(states)
    if metric_id == PRAGUE_OWNER:
        owners = _owners(con)
        homes = dict(con.execute('SELECT client_id, district_id FROM client'))
        states = [state for account, state in con.execute('SELECT account_id, status FROM loan')
                  if district_region[homes[owners[account]]] == 'Prague']
        return _distress_counts(states)
    raise ValueError('Unknown cohort contract')


def render(metric_id, observed):
    if metric_id == AGE_BANDS:
        bands = {label: {'loan_count': count, 'approved_amount': amount}
                 for label, count, amount in zip(('<30', '30-49', '50+'), observed[::2], observed[1::2])}
        return bands, {'total_loans': sum(observed[::2])}
    if metric_id == CLOSING_BALANCE:
        accounts, net, positive, negative, zero, credits, debits, zero_sum = observed
        return net, {'account_count': accounts, 'positive_account_count': positive,
                     'negative_account_count': negative, 'zero_account_count': zero,
                     'positive_balance_sum': credits, 'negative_balance_sum': debits,
                     'zero_balance_sum': zero_sum}
    if metric_id == FEMALE_OWNER:
        loans, total = observed
        return total / loans, {'loan_count': loans, 'approved_amount_sum': total}
    if metric_id in (MORAVIA, PRAGUE_OWNER):
        numerator, denominator = observed
        return numerator / denominator, {'numerator': numerator, 'denominator': denominator}
    raise ValueError('Unknown cohort contract')
