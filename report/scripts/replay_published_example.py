"""Replay the two DIN-SQL predictions displayed for Q177 in Wretblad et al., Fig. 8."""
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import sys

from compare_releases import load_cases

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from validation.reference import SNAPSHOT_SHA, snapshot

# Transcribed from the authors' published illustration, including its punctuation.
# Only the line wrapping and indents have been normalized. The authors' MIT
# license and attribution accompany the other release inputs in report/inputs/wretblad.
FIGURE = ('https://github.com/niklaswretblad/the-effects-of-noise-in-text-to-SQL/blob/'
          '6930cf6f9abaf50a3407f96b9facbda11835eec2/figures/synonym_example.png')
PRINTED = {
    'original_question': """SELECT
SUM(trans.amount)
client.gender
FROM trans
JOIN account ON trans.account_id = account.account_id
JOIN disp ON account.account_id = disp.account_id
JOIN client ON disp.client_id = client.client_id
WHERE trans.trans_id = 851 AND client.client_id = 4;""",
    'reworded_question': """SELECT
trans.balance
client.gender
FROM
trans
JOIN disp ON trans.account_id = disp.account_id
JOIN client ON disp.client_id = client.client_id
WHERE trans.trans_id = 851 AND client.client_id = 4;""",
}
RELEASES = {
    'original': 'financial.json',
    'sql_only': 'financial_corrected_sql.json',
    'fully_corrected': 'financial_corrected.json',
}


def execute_display(con, sql, references):
    try:
        rows = Counter(con.execute(sql))
    except sqlite3.OperationalError as exc:
        if 'syntax error' not in str(exc).lower():
            raise
        return {'execution': 'syntax_error', 'row_count': None, 'matches_reference': None}
    return {'execution': 'ok', 'row_count': sum(rows.values()),
            'matches_reference': {release: rows == gold for release, gold in references.items()}}


def replay(database):
    data = REPO / 'report/inputs/wretblad/datasets'
    gold_sql = {release: load_cases(data / path)[177]['SQL'] for release, path in RELEASES.items()}
    evidence = []
    with snapshot(REPO / 'data/financial.sqlite.gz', db=database) as con:
        references = {release: Counter(con.execute(sql)) for release, sql in gold_sql.items()}
        for question, printed in PRINTED.items():
            corrected = printed.replace('\nclient.gender', ',\nclient.gender', 1)
            if len(corrected) != len(printed) + 1:
                raise ValueError('Expected one new SELECT-list separator.')
            evidence.append({
                'displayed_prediction': question,
                'transcription_sha256': sha256(printed.encode()).hexdigest(),
                'as_printed': execute_display(con, printed, references),
                'one_comma_inserted': execute_display(con, corrected, references),
            })
    return {
        'paper_version': 'arXiv:2402.12243v4', 'figure': 8, 'question_id': 177,
        'source_figure': FIGURE,
        'source_figure_sha256': 'f6ae8ae823b8ac73e2aea75877037dbdbbd55b087ecbc49d1d9f4c98b2e94852',
        'snapshot_sha256': SNAPSHOT_SHA, 'model_label_in_figure': 'DIN-SQL (GPT-3.5)',
        'reference_outputs_equal_across_three_releases': all(
            rows == references['original'] for rows in references.values()),
        'examples': evidence,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', type=Path, help='Pre-unpacked, checksum-matched snapshot.')
    parser.add_argument('--check', type=Path, help='Compare with a previously saved evidence file.')
    args = parser.parse_args()
    result = replay(args.db)
    if args.check:
        if result != json.loads(args.check.read_bytes()):
            raise SystemExit('Figure 8 replay differs from the archived evidence.')
        print('Figure 8 verified on Q177, as printed and with one comma inserted in each query.')
    else:
        print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
