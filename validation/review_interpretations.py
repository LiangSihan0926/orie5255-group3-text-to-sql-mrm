"""Compare the 18 disputed saved results against explicit financial interpretations."""
import argparse
import csv
import math
import re
from pathlib import Path

from . import reference
from .run import ROOT, verify_inputs


def review():
    verify_inputs(ROOT)
    with reference.snapshot(ROOT / 'data/financial.sqlite.gz') as con:
        refs = reference.recompute(con)['illustrations']
    weights = refs['T7_weight_sensitivity']
    vintages = refs['T8_vintage_sensitivity']
    path = ROOT / 'archive/text2sql_bird/results_adjudicated.csv'
    output = []
    with path.open(newline='', encoding='utf-8') as f:
        for r in csv.DictReader(f):
            if r['adjudicated'] != 'REVIEW':
                continue
            cid = r['id']
            # Each printed tuple in these two cases contains only numbers. Preserve
            # the year and row boundaries: matching a rate in the wrong year fails.
            visible = [tuple(float(x.strip()) for x in group.split(','))
                       for group in re.findall(r'\(([^()]*)\)', r['llm_result'])]
            if cid == 'T7' and [len(t) for t in visible] == [1]:
                primary = close(visible[0][0], weights['count_weighted_percent'])
                alternate = close(visible[0][0], weights['amount_weighted_percent'])
                interpretation = 'approved-amount weight'
                reference_in_output = False  # only the scalar is present
                supporting = 'excluded loan count (8)'
            elif cid == 'T8' and len(visible) == len(vintages) == 2:
                def matches(field):
                    return all(len(row) >= 2 and row[0] == int(v['year']) and close(row[-1], v[field])
                               for row, v in zip(visible, vintages))
                primary = matches('finished_b_count_share')
                alternate = matches('all_bd_count_share')
                interpretation = 'B/D count share of all originations'
                reference_in_output = all(len(row) == 4 and row[2] == v['originated_loans']
                                          for row, v in zip(visible, vintages))
                supporting = 'originated loan count by vintage (101, 196)'
            else:
                raise ValueError(f'Unexpected review case or display: {cid}')
            output.append(dict(case_id=cid, model=r['model'], config=r['config'], repeat=r['run'],
                               action=r['action'], numeric_match_archived_definition=primary,
                               alternate_definition=interpretation, numeric_match_alternative=alternate,
                               supporting_count_checked=supporting,
                               supporting_count_in_saved_result=reference_in_output))
    return output


def close(observed, target):
    return math.isclose(observed, target, rel_tol=0, abs_tol=0.00005)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'evidence/interpretation_review.csv')
    path = parser.parse_args().output
    rows = review()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, rows[0].keys(), lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


if __name__ == '__main__':
    main()
