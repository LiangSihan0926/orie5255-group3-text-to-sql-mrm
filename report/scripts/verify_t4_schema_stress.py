"""Exercise the two repository T4 templates on an in-memory copy of BIRD's table definitions.

python3 verify_t4_schema_stress.py --repo /path/to/repo [--check t4_schema_stress.json]
Fixture data and the coverage signal are synthetic. No model or production authorization is invoked.
"""
from argparse import ArgumentParser
import ast
import gzip
from hashlib import sha256
import json
from pathlib import Path
import shutil
import sqlite3
from tempfile import TemporaryDirectory


DB_SHA = 'd15d89cdb068a202b6f2b99342af44dffc1d52545b39ceaf62efdc0ba570101e'
CONTROL_SHA = 'c2fb3ce80e6b00d2d10fcc018a1a95ae66f9e383a6da4b76dcff8d957f504a8b'
TABLES = ('district', 'account', 'loan', 'trans')


def inputs(repo):
    control = (repo / 'validation/controls.py').read_bytes()
    if sha256(control).hexdigest() != CONTROL_SHA:
        raise ValueError('Unexpected T4 control version')
    templates = {node.targets[0].id: ast.literal_eval(node.value)
                 for node in ast.parse(control).body if isinstance(node, ast.Assign)
                 and isinstance(node.targets[0], ast.Name) and node.targets[0].id in ('IN', 'EXISTS')}
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / 'financial.sqlite'
        with gzip.open(repo / 'data/financial.sqlite.gz', 'rb') as source, path.open('wb') as dest:
            shutil.copyfileobj(source, dest)
        if sha256(path.read_bytes()).hexdigest() != DB_SHA:
            raise ValueError('Unexpected source database')
        source = sqlite3.connect(path.as_uri() + '?mode=ro&immutable=1', uri=True)
        try:
            ddl = {name: source.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
                                        (name,)).fetchone()[0] for name in TABLES}
            # Include any explicitly defined indexes, including potential extra uniqueness constraints.
            indexes = [sql for name, sql in source.execute(
                "SELECT tbl_name, sql FROM sqlite_master WHERE type='index' AND sql IS NOT NULL ORDER BY name"
            ) if name in TABLES]
            n, accts = source.execute('SELECT COUNT(*), COUNT(DISTINCT account_id) FROM loan').fetchone()
        finally:
            source.close()
    return templates, ddl, indexes, {'loans': n, 'distinct_loan_accounts': accts}


def fixture(ddl, indexes, extra_loan, event_accounts):
    db = sqlite3.connect(':memory:')
    db.execute('PRAGMA foreign_keys=ON')
    for sql in [*ddl.values(), *indexes]:
        db.execute(sql)
    db.execute("""INSERT INTO district VALUES (1,'Synthetic','Synthetic','0','0','0','0',
                                              0,'0',0.0,0,0.0,0.0,0,0,0)""")
    db.executemany("INSERT INTO account VALUES (?,1,'MONTHLY','1995-01-01')", [(1,), (2,), (3,)])
    loans = [(1, 1, 100), (2, 2, 200)]
    if extra_loan:
        loans.append((3, *extra_loan))
    db.executemany("""INSERT INTO loan(loan_id,account_id,amount,date,duration,payments,status)
                      VALUES (?,?,?,'1996-01-01',12,10,'A')""", loans)
    events = [(1, 1, 'OTHER')] + [(n, account, 'VYBER KARTOU') for n, account in enumerate(event_accounts, 2)]
    db.executemany("""INSERT INTO trans(trans_id,account_id,operation,date,type,amount,balance)
                      VALUES (?,?,?,'1996-02-01','VYDAJ',1,100)""", events)
    if db.execute('PRAGMA foreign_key_check').fetchall():
        raise ValueError('Fixture violates the real schema')
    db.execute('PRAGMA query_only=ON')
    return db


def run(repo):
    templates, ddl, indexes, source_counts = inputs(repo)
    # Each fixture starts from the same two loans (100 on A, 200 on B).
    # Cases specify added loan (account, amount), qualifying event account(s), external coverage and oracle total.
    cases = [
        ('empty_verified', None, [], 'verified', 0),
        ('empty_unverified', None, [], 'unknown', None),
        ('one_eligible', None, [1], 'verified', 100),
        ('one_eligible_incomplete', None, [1], 'incomplete', None),
        ('repeat_withdrawal', None, [1, 1], 'verified', 100),
        ('two_loans_one_account', (1, 60), [1], 'verified', 160),
        ('distinct_equal_amounts', (3, 100), [1, 3], 'verified', 200),
    ]
    eligible = """FROM loan l WHERE EXISTS (SELECT 1 FROM trans t WHERE t.account_id=l.account_id
                                             AND t.operation='VYBER KARTOU')"""
    faults = {
        'direct_event_join': """SELECT SUM(l.amount) FROM loan l JOIN trans t ON t.account_id=l.account_id
                                WHERE t.operation='VYBER KARTOU'""",
        'one_maximum_per_account': f'SELECT SUM(x) FROM (SELECT MAX(l.amount) AS x {eligible} GROUP BY l.account_id)',
        'deduplicate_amount': f'SELECT SUM(DISTINCT l.amount) {eligible}',
    }
    results = []
    for name, loan, events, coverage, expected in cases:
        db = fixture(ddl, indexes, loan, events)
        try:
            raw = {key: db.execute(sql).fetchone()[0] for key, sql in templates.items()}
            wrong = {key: db.execute(sql).fetchone()[0] for key, sql in faults.items()}
            expected_raw = None if not events else sum(amount for account, amount in
                                                       [(1, 100), (2, 200)] + ([loan] if loan else [])
                                                       if account in set(events))
            if raw != {'IN': expected_raw, 'EXISTS': expected_raw}:
                raise ValueError(f'Templates missed the expected visible total for {name}')
            value = None
            # Hypothetical gate: an independent upstream signal attests that both sources cover the contract.
            # Do not infer completeness from the row count, the SQL result, or the byte hash alone.
            if coverage == 'verified':
                value = db.execute(f'SELECT COALESCE(SUM(l.amount),0) {eligible}').fetchone()[0]
            if value != expected:
                raise ValueError(f'Coverage-gated measure missed the case oracle for {name}')
            results.append(dict(scenario=name, coverage=coverage, expected_gated_value=expected, vetted_templates=raw,
                                proposed_action='return' if coverage == 'verified' else 'hold',
                                proposed_value=value, fault_examples=wrong))
        finally:
            db.close()
    return dict(source_db_sha256=DB_SHA, source_control_sha256=CONTROL_SHA, source_snapshot=source_counts,
                tables_reused=list(ddl), enforced_foreign_keys=True,
                schema_allows_multiple_loans_per_account=True, scenarios=results)


if __name__ == '__main__':
    p = ArgumentParser(description=__doc__)
    p.add_argument('--repo', type=Path, required=True)
    p.add_argument('--check', type=Path)
    args = p.parse_args()
    observed = run(args.repo.resolve())
    if args.check:
        if observed != json.loads(args.check.read_text()):
            raise SystemExit('T4 schema stress results differ')
        print('All schema stress results agree.')
    else:
        print(json.dumps(observed, indent=2))
