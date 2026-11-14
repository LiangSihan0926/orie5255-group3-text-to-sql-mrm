"""Run the offline validation: python -m validation.run [--db /path/financial.sqlite]."""
from argparse import ArgumentParser
from pathlib import Path
from hashlib import sha256
import csv
import gzip
import json
from . import audit, controls, reference

ROOT=Path(__file__).resolve().parents[1]

def verify_inputs(root):
    manifest=json.loads((root/'archive/manifest.json').read_text())
    for item in manifest['files']:
        f=root/item['repository_path']
        if item.get('hash_applies_to')=='uncompressed bytes':
            # Raw database SHA is verified by snapshot() before any query is run.
            assert f.is_file()
        elif sha256(f.read_bytes()).hexdigest()!=item['sha256']:
            raise ValueError(f'Archived input changed: {item["repository_path"]}')

def run(root=ROOT,db=None):
    verify_inputs(root)
    archive=root/'archive/text2sql_bird'
    rows=audit.archive_runs(archive)
    metrics=audit.summarize(archive,rows)
    with reference.snapshot(root/'data/financial.sqlite.gz',db=db) as con:
        refs=reference.recompute(con)
    comparisons=audit.compare_references(archive,refs)
    mismatches=[r['id'] for r in comparisons if not r['recorded_match']]
    if mismatches:
        raise ValueError(f'Reference comparison disagrees on {", ".join(mismatches)}')
    return dict(pilot=metrics,references=refs,reference_comparison=comparisons,
                t4_archive_replay=controls.replay_t4(rows),
                t4_fixtures={'expected':controls.SCENARIOS,'candidates':controls.fixtures()})

def write(report,out):
    out.mkdir(exist_ok=True,parents=True)
    (out/'validation_results.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
    for filename,records in (
        ('pilot_cells.csv',report['pilot']['cells']),
        ('reference_comparison.csv',report['reference_comparison']),
        ('t4_archive_replay.csv',report['t4_archive_replay']),
    ):
        with (out/filename).open('w',encoding='utf-8',newline='') as f:
            w=csv.DictWriter(f,fieldnames=records[0].keys(),lineterminator='\n')
            w.writeheader()
            w.writerows(records)

def main():
    p=ArgumentParser(description=__doc__)
    p.add_argument('--db',type=Path,help='Optional unpacked snapshot; must match the original hash.')
    p.add_argument('--output',type=Path,default=ROOT/'evidence')
    a=p.parse_args()
    report=run(db=a.db)
    write(report,a.output)
    print(f'{report["pilot"]["runs"]} runs reconciled; {len(report["reference_comparison"])} reference cases checked.')
    print(a.output/'validation_results.json')

if __name__=='__main__':
    main()
