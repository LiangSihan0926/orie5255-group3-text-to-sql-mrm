"""Recount Tables 1 and 2 on the paper authors' released financial annotations."""
import argparse
import csv
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path

PAPER_TABLE_1 = {'any': 52, 'question': 44, 'sql': 22}
PAPER_TABLE_2 = [23, 17, 22, 2, 7, 1]
TYPES = ['spelling_or_syntax', 'vagueness', 'incorrect_sql', 'synonyms', 'capitalization', 'no_mapping']


def read_labels(annotation, eligible):
    with annotation.open(encoding='utf-8-sig', newline='') as f:
        rows = [r for r in csv.DictReader(f) if r['Question ID'].strip().isdigit()]
    labels_by_id = {
        int(r['Question ID']): {int(x.strip()) for x in r['Error Category'].split(',') if x.strip()}
        for r in rows
    }
    if len(rows) != 106 or len(labels_by_id) != len(rows) or set(labels_by_id) != eligible:
        raise ValueError('Expected one annotation per official financial ID')
    for item, labels in labels_by_id.items():
        if not labels <= set(range(1, 7)):
            raise ValueError(f'Unknown label on item {item}')
    return labels_by_id


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('authors', type=Path)
    parser.add_argument('--check', type=Path)
    args = parser.parse_args()
    annotation = args.authors / 'annotations/financial_annotations.csv'
    original = json.loads((args.authors / 'datasets/financial.json').read_text())
    labels_by_id = read_labels(annotation, {item['question_id'] for item in original})
    counts = Counter()
    table1 = dict(any=0, question=0, sql=0)
    for labels in labels_by_id.values():
        counts.update(labels)
        table1['any'] += bool(labels)
        table1['question'] += bool(labels - {3})
        table1['sql'] += 3 in labels
    both = table1['question'] + table1['sql'] - table1['any']
    report = {'annotation_sha256': sha256(annotation.read_bytes()).hexdigest(), 'items': len(labels_by_id),
              'financial_table1_published': PAPER_TABLE_1, 'financial_table1_recount': table1, 'overlap': both,
              'financial_table2_published': dict(zip(TYPES, PAPER_TABLE_2)),
              'financial_table2_recount': {name: counts[k] for k, name in enumerate(TYPES, 1)}}
    if args.check:
        if report != json.loads(args.check.read_text()):
            raise SystemExit('Annotation evidence differs')
        print('Financial annotation recount verified.')
    else:
        print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
