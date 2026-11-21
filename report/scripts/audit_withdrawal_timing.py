"""Compare snapshot-wide card withdrawals with withdrawals recorded by loan approval."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from validation import reference

GROUPS = ('before_approval', 'on_approval_date', 'after_approval', 'no_recorded_withdrawal')
EVENT = 'VYBER KARTOU'
GROUP_SQL = """
WITH first_event AS (
    SELECT account_id, MIN(date) AS first_date
    FROM trans WHERE operation = ? AND date <= ? GROUP BY account_id
), classified AS (
    SELECT l.amount,
           CASE WHEN e.first_date IS NULL THEN 'no_recorded_withdrawal'
                WHEN e.first_date < l.date THEN 'before_approval'
                WHEN e.first_date = l.date THEN 'on_approval_date'
                ELSE 'after_approval' END AS timing
    FROM loan AS l LEFT JOIN first_event AS e ON e.account_id = l.account_id
    WHERE l.date <= ?
)
SELECT timing, COUNT(*), SUM(amount) FROM classified GROUP BY timing
"""


def measure(con, cutoff):
    sql = {name: (0, 0) for name in GROUPS}
    for name, count, total in con.execute(GROUP_SQL, (EVENT, cutoff, cutoff)):
        sql[name] = count, total

    first = {}
    for account, day, kind in con.execute('SELECT account_id, date, operation FROM trans'):
        if kind == EVENT and day <= cutoff and (account not in first or day < first[account]):
            first[account] = day
    totals = {name: [0, 0] for name in GROUPS}
    for account, day, amount in con.execute('SELECT account_id, date, amount FROM loan'):
        if day > cutoff:
            continue
        when = first.get(account)
        if when is None:
            group = 'no_recorded_withdrawal'
        elif when == day:
            group = 'on_approval_date'
        elif when < day:
            group = 'before_approval'
        else:
            group = 'after_approval'
        totals[group][0] += 1
        totals[group][1] += amount
    if any(tuple(totals[name]) != sql[name] for name in GROUPS):
        raise ValueError('The loan-level reconstruction differs from the grouped SQL.')
    return {name: {'loans': count, 'approved_principal_source_units': total}
            for name, (count, total) in sql.items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', type=Path)
    args = parser.parse_args()
    with reference.snapshot(ROOT / 'data/financial.sqlite.gz') as con:
        buckets = measure(con, reference.AS_OF)
    evidence = {
        'snapshot_sha256': reference.SNAPSHOT_SHA,
        'as_of': reference.AS_OF,
        'event': EVENT,
        'grain': 'one approved amount per loan',
        'comparison': 'first recorded qualifying event on its account versus loan.date (approval date)',
        'buckets': buckets,
    }
    if args.check:
        if evidence != json.loads(args.check.read_text(encoding='utf-8')):
            raise SystemExit('Withdrawal timing evidence differs from the pinned snapshot.')
        print('Withdrawal timing and principal agree for all four loan cohorts.')
    else:
        print(json.dumps(evidence, indent=2))


if __name__ == '__main__':
    main()
