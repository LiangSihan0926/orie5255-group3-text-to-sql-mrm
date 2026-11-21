"""Exercise a proposed provenance gate on small synthetic monthly SQLite snapshots."""
import argparse
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory

JAN = '2025-01-31'
FEB = '2025-02-28'
DDL = 'CREATE TABLE loan(loan_id INTEGER PRIMARY KEY, approval_date TEXT, amount INTEGER)'
QUERY = 'SELECT SUM(amount) FROM loan WHERE approval_date <= ?'


@dataclass(frozen=True)
class Source:
    path: Path
    digest: str


def make_snapshot(folder, version, rows):
    path = folder / (version + '.sqlite')
    con = sqlite3.connect(path)
    try:
        con.execute(DDL)
        con.executemany('INSERT INTO loan VALUES(?, ?, ?)', rows)
        con.commit()
    finally:
        con.close()
    return Source(path, sha256(path.read_bytes()).hexdigest())


def candidate(source, cutoff):
    # Derive the fingerprint at the read boundary rather than copying the expected version.
    actual_digest = sha256(source.path.read_bytes()).hexdigest()
    con = sqlite3.connect(source.path.resolve().as_uri() + '?mode=ro&immutable=1', uri=True)
    try:
        total = con.execute(QUERY, (cutoff,)).fetchone()[0]
    finally:
        con.close()
    return {'cutoff': cutoff, 'digest': actual_digest, 'total': total}


def audit():
    with TemporaryDirectory() as tmp:
        folder = Path(tmp)
        jan = make_snapshot(folder, 'jan', [(1, '2025-01-15', 100)])
        feb = make_snapshot(folder, 'feb', [(1, '2025-01-15', 100), (2, '2025-02-15', 60)])
        if jan.digest == feb.digest:
            raise ValueError('Fixture versions must differ')
        # Expected release version and financial cutoff are independent request fields.
        # A February snapshot can legitimately answer a January as-of question.
        cases = [
            ('historical_requested', jan, JAN, jan, JAN, None, 100, 'accept'),
            ('current_requested', feb, FEB, feb, FEB, None, 160, 'accept'),
            ('old_executor', feb, FEB, jan, FEB, None, 160, 'hold_source'),
            ('old_cache', feb, FEB, feb, FEB, (jan, FEB), 160, 'hold_cache'),
            ('wrong_cutoff', feb, FEB, feb, JAN, None, 160, 'hold_cutoff'),
            ('current_file_historical_cutoff', feb, JAN, feb, JAN, None, 100, 'accept'),
            ('old_cache_equal_numeric_total', feb, JAN, feb, JAN, (jan, JAN), 100, 'hold_cache'),
        ]
        rows = []
        for name, approved, intended_cutoff, executor, executed_cutoff, cached, expected_total, expected_action in cases:
            observed = candidate(executor, executed_cutoff)
            result = candidate(*cached) if cached else observed
            if observed['digest'] != approved.digest:
                action = 'hold_source'
            elif result['digest'] != approved.digest:
                action = 'hold_cache'
            elif observed['cutoff'] != intended_cutoff or result['cutoff'] != intended_cutoff:
                action = 'hold_cutoff'
            else:
                action = 'accept'
            if action != expected_action or (action == 'accept' and result['total'] != expected_total):
                raise AssertionError(name)
            rows.append(dict(case=name, requested_cutoff=intended_cutoff, candidate_total=result['total'],
                             reference_total=expected_total, action=action))
        return {'measure': 'approved amount in source units', 'identical_schema': True, 'cases': rows}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--check', type=Path)
    args = p.parse_args()
    report = audit()
    if args.check:
        if report != json.loads(args.check.read_text()):
            raise SystemExit('Snapshot binding evidence differs')
        print('Seven snapshot binding cases verified.')
    else:
        print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
