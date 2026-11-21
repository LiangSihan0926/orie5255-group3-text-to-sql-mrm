"""Recompute supplementary diagnostics from the frozen public repository (Python 3.9+).

python3 verify_archive_diagnostics.py --repo /path/to/orie5255-group3-text-to-sql-mrm
python3 verify_archive_diagnostics.py --repo /path/to/repo --check archive_diagnostics.json

Only fixed aggregate SELECTs run on the verified snapshot. No candidate SQL is executed.
The repository's python3 -B -m validation.run reproduces the wider 19-case reference set.
"""
import argparse
from collections import Counter
import csv
from decimal import Decimal
import gzip
from hashlib import sha256
from itertools import permutations
import json
from pathlib import Path
import re
import shutil
import sqlite3
import tempfile


DATABASE_SHA256 = 'd15d89cdb068a202b6f2b99342af44dffc1d52545b39ceaf62efdc0ba570101e'
CASE_IDS = [f'{prefix}{n}' for prefix, last in [('E', 3), ('T', 10), ('A', 3), ('X', 3)]
            for n in range(1, last + 1)]


def digest(path):
    h = sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def read_inputs(repo):
    archive = repo / 'archive' / 'text2sql_bird'
    manifest = json.loads((repo / 'archive' / 'manifest.json').read_text())
    hashes = {e['repository_path']: e['sha256'] for e in manifest['files']}

    def verified(path):
        if digest(path) != hashes[path.relative_to(repo).as_posix()]:
            raise ValueError(f'Archived file differs from its manifest: {path.name}')
        return path

    dictionary = verified(archive / 'metric_dictionary.yaml').read_text()
    with verified(archive / 'test_suite_results.csv').open(encoding='utf-8', newline='') as handle:
        references = {r['id']: r['gold_result'] for r in csv.DictReader(handle) if r['id'][0] in ('E', 'T')}
    rows = []
    for model in ('gpt-4.1', 'gpt-4o-mini'):
        for repair, suffix in (('off', ''), ('on', '_repair2')):
            file = verified(archive / f'llm_runs_openai_{model}{suffix}.csv')
            with file.open(encoding='utf-8', newline='') as f:
                records = list(csv.DictReader(f))
            found = Counter((r['id'], r['condition'], r['run']) for r in records)
            expected = Counter((cid, p, str(i)) for cid in CASE_IDS
                               for p in ('baseline', 'dict') for i in (1, 2, 3))
            if found != expected:
                raise ValueError(f'Missing or duplicate cells in {file.name}')
            rows.extend(dict(r, model=model, repair=repair) for r in records)
    return rows, dictionary, references


def dictionary_audit(db, dictionary):
    expressions = {
        'bad_loan_count_share': "COUNT(status IN ('B','D')) / COUNT(*)",
        'finished_unpaid_count_share': "COUNT(status='B') / COUNT(status IN ('A','B'))",
        'running_delinquent_count_share': "COUNT(status='D') / COUNT(status IN ('C','D'))",
        'active_at_1996_year_end': "date(date, '+duration months')",
    }
    if any(expr not in dictionary for expr in expressions.values()):
        raise ValueError('Dictionary text differs from the version under study')

    status = dict(db.execute('SELECT status, COUNT(*) FROM loan GROUP BY status'))
    loans = sum(status.values())
    literal = db.execute("""
        SELECT COUNT(status IN ('B','D')) / COUNT(*),
               COUNT(status='B') / COUNT(status IN ('A','B')),
               COUNT(status='D') / COUNT(status IN ('C','D')) FROM loan
    """).fetchone()
    corrected = db.execute("""
        SELECT 1.0 * SUM(CASE WHEN status IN ('B','D') THEN 1 ELSE 0 END) / NULLIF(COUNT(*),0),
               1.0 * SUM(CASE WHEN status='B' THEN 1 ELSE 0 END) /
                    NULLIF(SUM(CASE WHEN status IN ('A','B') THEN 1 ELSE 0 END),0),
               1.0 * SUM(CASE WHEN status='D' THEN 1 ELSE 0 END) /
                    NULLIF(SUM(CASE WHEN status IN ('C','D') THEN 1 ELSE 0 END),0) FROM loan
    """).fetchone()
    terms = [(status['B'] + status['D'], loans), (status['B'], status['A'] + status['B']),
             (status['D'], status['C'] + status['D'])]
    result = {}
    for name, value, reference, (num, den) in zip(expressions, literal, corrected, terms):
        if reference != num / den:
            raise ValueError(f'Conditional aggregation disagrees with status counts for {name}')
        result[name] = dict(dictionary_expression=expressions[name], literal_fraction=value,
                            intended_numerator=num, intended_denominator=den, intended_fraction=reference)
    nulls, literal_n, corrected_n = db.execute("""
        SELECT COUNT(*) - COUNT(date(date, '+duration months')),
               COUNT(CASE WHEN date <= :asof AND date(date, '+duration months') > :asof THEN 1 END),
               COUNT(CASE WHEN date <= :asof AND date(date, '+' || duration || ' months') > :asof
                          THEN 1 END) FROM loan
    """, {'asof': '1996-12-31'}).fetchone()
    result['active_at_1996_year_end'] = dict(dictionary_expression=expressions['active_at_1996_year_end'],
                                            rows_with_null_literal_maturity=nulls, loans=loans,
                                            literal_active_count=literal_n, scheduled_active_count=corrected_n)
    return result


def is_candidate(row):
    return (row['id'][0] in ('E', 'T') and row['action'] == 'answer' and row['sql']
            and row['llm_result'] and not any(row[k] for k in ('guardrail', 'exec_error', 'n8_flag')))


def summarize(rows):
    return dict(candidates=len(rows), key_matches=sum(r['result_match'] == 'True' for r in rows),
                key_mismatches=sum(r['result_match'] == 'False' for r in rows))


def case_key(row):
    return [row['model'], row['condition'], row['repair'], int(row['run']), row['id']]


def parse_display(display):
    if not re.fullmatch(r'\([^()]+\)(?: \([^()]+\))*', display):
        raise ValueError(f'Incomplete result display: {display}')
    def value(cell):
        if re.fullmatch(r'-?\d+(?:\.\d+)?', cell):
            return Decimal(cell)
        return cell
    return [tuple(value(cell.strip()) for cell in group.split(','))
            for group in re.findall(r'\(([^()]*)\)', display)]


def recheck_visible_keys(candidates, references):
    """Compare full displayed row multisets at saved precision. The display omits SQL types and labels."""
    counts = Counter()
    for row in candidates:
        cid = row['id']
        key_columns = {'E1': (0, 1), 'T8': (0, 3)}.get(cid, (0,))
        reference = parse_display(references[cid])
        observed = parse_display(row['llm_result'])
        expected = Counter(tuple(x[k] for k in key_columns) for x in reference)
        matched = any(
            Counter(tuple(x[k] for k in cols) for x in observed) == expected
            for cols in permutations(range(len(observed[0])), len(key_columns))
        )
        if matched != (row['result_match'] == 'True'):
            raise ValueError(f'Displayed result and original label disagree: {case_key(row)}')
        counts['matches' if matched else 'mismatches'] += 1
    return dict(counts)


def run(repo):
    rows, dictionary, references = read_inputs(repo)
    numeric = [r for r in rows if r['id'][0] in ('E', 'T')]
    candidates = [r for r in numeric if is_candidate(r)]
    if any(r['result_match'] not in ('True', 'False') for r in candidates):
        raise ValueError('An eligible candidate lacks a comparison label')
    missing_or_zero = [r for r in candidates if re.fullmatch(r'\((?:None|0(?:\.0+)?)\)', r['llm_result'])]
    filtered = [r for r in candidates if r not in missing_or_zero]
    by_mode = {k: summarize([r for r in candidates if r['repair'] == k]) for k in ('off', 'on')}

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / 'financial.sqlite'
        with gzip.open(repo / 'data' / 'financial.sqlite.gz', 'rb') as src, path.open('wb') as out:
            shutil.copyfileobj(src, out)
        if digest(path) != DATABASE_SHA256:
            raise ValueError('Unexpected uncompressed database hash')
        db = sqlite3.connect(path.as_uri() + '?mode=ro&immutable=1', uri=True)
        try:
            dictionary_result = dictionary_audit(db, dictionary)
            t4 = db.execute("""SELECT SUM(l.amount) FROM loan AS l WHERE l.account_id IN (
                SELECT DISTINCT t.account_id FROM trans AS t WHERE t.operation='VYBER KARTOU')
            """).fetchone()[0]
            t9 = db.execute("""SELECT SUM(balance) FROM (
                SELECT balance, ROW_NUMBER() OVER (PARTITION BY account_id ORDER BY date DESC, trans_id DESC) AS k
                FROM trans WHERE date <= '1998-12-31') WHERE k=1""").fetchone()[0]
            t10 = db.execute('SELECT SUM(amount) FROM loan').fetchone()[0]
            t3 = dict(db.execute("""SELECT kind, AVG(amount) FROM (
                SELECT 'all_female_links' AS kind, l.amount FROM loan l JOIN disp d USING(account_id)
                JOIN client c USING(client_id) WHERE c.gender='F'
                UNION ALL
                SELECT 'female_owners', l.amount FROM loan l JOIN disp d USING(account_id)
                JOIN client c USING(client_id) WHERE c.gender='F' AND d.type='OWNER'
                ) GROUP BY kind"""))
        finally:
            db.close()

    expected = {'T4': t4, 'T6': dictionary_result['active_at_1996_year_end']['scheduled_active_count'], 'T9': t9}
    integer_misses = {}
    for cid, ref in expected.items():
        cohort = [r for r in candidates if r['id'] == cid]
        values = []
        for r in cohort:
            match = re.fullmatch(r'\((-?\d+)\)', r['llm_result'])
            if not match:
                raise ValueError(f'Cannot interpret {cid} display as one integer')
            value = int(match.group(1))
            if (value == ref) != (r['result_match'] == 'True'):
                raise ValueError(f'Integer recomputation disagrees with an archived {cid} key label')
            values.append(value)
        integer_misses[cid] = dict(reference=ref, candidates=len(values), wrong=sum(x != ref for x in values))

    currency = {}
    for prompt in ('baseline', 'dict'):
        cohort = [r for r in candidates if r['id'] == 'T10' and r['condition'] == prompt]
        currency[prompt] = dict(requests=len(cohort), raw_sum_matches=sum(r['llm_result'] == f'({t10})' for r in cohort),
                                strict_passes=sum(r['verdict'] == 'PASS' for r in cohort),
                                assumptions_say_us_dollars=sum('us dollars' in r['assumptions'].lower() for r in cohort),
                                assumptions_say_czk=sum('czk' in r['assumptions'].lower() for r in cohort),
                                assumptions_mention_fx_or_rate=sum(bool(re.search(
                                    r'\b(fx|exchange rate|conversion rate)\b', r['assumptions'], re.I)) for r in cohort))
    t6_literal = [case_key(r) for r in rows if r['id'] == 'T6' and "'+duration months'" in r['sql']]
    t8_prose = [case_key(r) for r in rows if r['id'] == 'T8' and r['verdict'] == 'PASS'
                and re.search(r"count\(status\s*=\s*'b'\)", r['assumptions'], re.I)]
    t3_misses = [r for r in candidates if r['id'] == 'T3' and r['result_match'] == 'False']
    t3.update(relative_difference=(t3['all_female_links'] / t3['female_owners'] - 1),
              mismatching_candidates=len(t3_misses),
              displays_reproducing_all_links=sum(r['llm_result'] == f"({t3['all_female_links']:.4f})" for r in t3_misses))
    return dict(
        snapshot_sha256=DATABASE_SHA256, final_records=len(rows), numeric_requests=len(numeric),
        archived_verdicts=dict(Counter(r['verdict'] for r in rows)),
        independently_rescored_display_keys=recheck_visible_keys(candidates, references),
        dictionary_sql_diagnostics=dictionary_result,
        keys_for_t6_final_sql_with_literal_modifier=t6_literal,
        keys_for_t8_strict_pass_with_count_boolean_in_explanation=t8_prose,
        numeric_candidate_sensitivity=dict(original=summarize(candidates), original_by_repair=by_mode,
            visible_null_or_zero_scalar=summarize(missing_or_zero),
            excluded_by_display_and_repair=dict(Counter(f"{r['llm_result']} / {r['repair']}" for r in missing_or_zero)),
            after_excluding_visible_null_or_zero_scalar=summarize(filtered)),
        exact_integer_diagnostics=integer_misses, t3_owner_sensitivity=t3, t10_denominations=currency,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--check', type=Path, help='Verify equality with the supplied diagnostic JSON')
    args = parser.parse_args()
    report = run(args.repo.resolve())
    if args.check:
        if report != json.loads(args.check.read_text()):
            raise SystemExit('Diagnostic JSON differs from the recomputed values')
        print('Diagnostic JSON agrees with the frozen logs and database.')
    else:
        print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
