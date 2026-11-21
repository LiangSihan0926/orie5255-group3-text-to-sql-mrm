"""Reconcile the archived score sheets with the raw records, without API calls or SQL execution."""
from collections import Counter
import csv
import re

MODELS=('gpt-4.1','gpt-4o-mini')
REPAIR_MODES=('off','on')
PROMPTS=('baseline','dict')
CASE_IDS=tuple(f'{p}{i}' for p,n in (('E',3),('T',10),('A',3),('X',3)) for i in range(1,n+1))

def read_csv(p):
    with p.open(encoding='utf-8',newline='') as f:
        return list(csv.DictReader(f))

def archive_runs(archive):
    rows=[]
    for model in MODELS:
        for rep in REPAIR_MODES:
            suffix='_repair2' if rep=='on' else ''
            part=read_csv(archive/f'llm_runs_openai_{model}{suffix}.csv')
            expected={(p,r,q) for p in PROMPTS for r in ('1','2','3') for q in CASE_IDS}
            actual={(r['condition'],r['run'],r['id']) for r in part}
            if len(part)!=len(expected) or actual!=expected:
                raise ValueError(f'Incomplete or duplicate factorial cells: {model}/{rep}')
            buckets=Counter((r['condition'],r['category'].split(':')[0],r['verdict']=='PASS') for r in part)
            summary=read_csv(archive/f'llm_summary_openai_{model}{suffix}.csv')
            assert len(summary)==8
            for s in summary:
                n=buckets[s['condition'],s['group'],True]
                assert int(s['pass'])==n and int(s['total'])==n+buckets[s['condition'],s['group'],False]
            rows.extend(dict(r,model=model,repair=rep) for r in part)
    return rows

def runtime_ok(r):
    # Proxy for candidate release from the saved final trace, not a production event.
    return bool(r['sql'] and r['llm_result'] and not any(r[k] for k in ('guardrail','exec_error','n8_flag')))

def numeric_funnel(rows):
    """Separate observable answer coverage from the archive's key-result labels."""
    answers=[r for r in rows if r['action']=='answer' and runtime_ok(r)]
    matched=sum(r['result_match']=='True' for r in answers)
    mismatched=sum(r['result_match']=='False' for r in answers)
    return dict(requests=len(rows),runtime_clean=len(answers),
                key_match=matched,key_mismatch=mismatched,
                comparable_missing=len(answers)-matched-mismatched,
                strict_pass=sum(r['verdict']=='PASS' for r in rows))

def repeat_stability(rows):
    """A block is one case and configuration with its three archived repeats."""
    blocks=Counter((r['id'],r['model'],r['condition'],r['repair']) for r in rows)
    passes=Counter((r['id'],r['model'],r['condition'],r['repair'])
                   for r in rows if r['verdict']=='PASS')
    assert set(blocks.values())=={3}
    counts=Counter(passes[key] for key in blocks)
    return {str(i):counts[i] for i in range(4)}

def summarize(archive,rows):
    cells=[]
    numeric_by_config=[]
    for m in MODELS:
        for p in PROMPTS:
            for rep in REPAIR_MODES:
                sub=[r for r in rows if (r['model'],r['condition'],r['repair'])==(m,p,rep)]
                numeric_by_config.append(dict(model=m,prompt=p,repair=rep,
                    **numeric_funnel([r for r in sub if r['id'][0] in ('E','T')])))
                for prefix in ('E','T','A','X'):
                    selected=[r for r in sub if r['id'].startswith(prefix)]
                    cells.append(dict(model=m,prompt=p,repair=rep,group=prefix,total=len(selected),
                                      strict_pass=sum(r['verdict']=='PASS' for r in selected)))
    numeric=[r for r in rows if r['id'][0] in ('E','T')]
    runtime=[r for r in numeric if runtime_ok(r) and r['action']=='answer']
    mismatch=[r for r in runtime if r['result_match']=='False']
    repair=[r for r in rows if r['repair']=='on']
    policy=[r for r in repair if r['id'].startswith('X')]
    policy_by_case=[]
    for cid in ('X1','X2','X3'):
        group=[r for r in policy if r['id']==cid]
        candidates=[r for r in group if runtime_ok(r)]
        matches=sum(r['result_match']=='True' for r in candidates)
        misses=sum(r['result_match']=='False' for r in candidates)
        no_sql=sum(not r['sql'] for r in group)
        policy_by_case.append(dict(id=cid,requests=len(group),
            action_pass=sum(r['verdict']=='PASS' for r in group),
            no_sql=no_sql,runtime_clean_key_match=matches,runtime_clean_key_mismatch=misses,
            sql_without_comparable_runtime_clean_result=len(group)-no_sql-matches-misses))
    adj=read_csv(archive/'results_adjudicated.csv')
    assert len(adj)==len(rows)
    adj_key={(r['model'].removeprefix('openai_'),r['config'],r['run'],r['id']):r for r in adj}
    for r in rows:
        label=r['condition']+' / '+('repair' if r['repair']=='on' else 'no repair')
        a=adj_key[r['model'],label,r['run'],r['id']]
        assert all(r[k]==a[k] for k in ('verdict','action','sql','llm_result','repair_trace'))
    open_mismatches=[
        r for r in mismatch
        if adj_key[r['model'],r['condition']+' / '+('repair' if r['repair']=='on' else 'no repair'),
                   r['run'],r['id']]['adjudicated']=='REVIEW'
    ]
    retried=[r for r in numeric if r['repair']=='on' and int(r['attempts'])>1]
    return {
        'runs':len(rows), 'questions':len(CASE_IDS), 'attempts_from_archived_counter':sum(int(r['attempts']) for r in rows),
        'strict_verdicts':dict(Counter(r['verdict'] for r in rows)),
        'numeric_candidates':{
            'requests':len(numeric),
            'action_answer_and_runtime_clean':len(runtime),
            'key_result_mismatch_among_runtime_clean':len(mismatch),
            'rule_labeled_review_within_clean_mismatches':dict(Counter(r['id'] for r in open_mismatches)),
            'mismatch_by_case':dict(sorted(Counter(r['id'] for r in mismatch).items())),
        },
        'numeric_by_family':{label:numeric_funnel([r for r in numeric if r['id'][0]==prefix])
                             for prefix,label in (('E','routine'),('T','trap'))},
        'numeric_by_configuration':numeric_by_config,
        'trap_strict_repeat_blocks':repeat_stability([r for r in numeric if r['id'][0]=='T']),
        'retried_numeric':numeric_funnel(retried),
        'numeric_key_match_with_failed_caveat':dict(Counter(
            r['id'] for r in runtime if r['result_match']=='True' and r['caveat_ok']=='False'
        )),
        'clarification_action_pass':sum(r['verdict']=='PASS' for r in rows if r['id'][0]=='A'),
        'clarification_requests':sum(r['id'][0]=='A' for r in rows),
        'repair_with_more_than_one_attempt':sum(int(r['attempts'])>1 for r in repair),
        'repair_policy':{
            'runs':len(policy),
            'strict_pass':sum(r['verdict']=='PASS' for r in policy),
            'no_sql':sum(not r['sql'] for r in policy),
            'returned_sql':sum(bool(r['sql']) for r in policy),
            'key_result_match':sum(r['result_match']=='True' for r in policy),
            'key_result_mismatch':sum(r['result_match']=='False' for r in policy),
        },
        'repair_policy_by_case':policy_by_case,
        'adjudication_transitions':dict(Counter(f"{r['verdict']} -> {r['adjudicated']}" for r in adj)),
        'review_by_case':dict(Counter(r['id'] for r in adj if r['adjudicated']=='REVIEW')),
        'cells':cells,
    }

def displayed_rows(text):
    """The archive renders small result tuples at four decimal places."""
    def value(s):
        s=s.strip()
        if s=='None':return None
        try:return int(s)
        except ValueError:pass
        try:return float(s)
        except ValueError:return s
    return [tuple(value(x) for x in row.split(',')) for row in re.findall(r'\(([^()]*)\)',text)]

def t4_amount_audit(rows, expected):
    """Grade the visible T4 scalar against the independent loan-grain integer total."""
    findings=[]
    for row in rows:
        if row['id']!='T4':
            continue
        amount=None
        classification='outside runtime-clean answer set'
        if row['action']=='answer' and runtime_ok(row):
            # The archived value is an integer tuple; leave other shapes unscorable.
            scalar=re.fullmatch(r'\((-?[0-9]+)\)',row['llm_result'].strip())
            if scalar:
                amount=int(scalar.group(1))
                classification='exact total' if amount==expected else 'wrong total'
            else:
                classification='unscorable amount'
        findings.append(dict(model=row['model'],prompt=row['condition'],repair=row['repair'],
            repeat=int(row['run']),observed_amount=amount,expected_amount=expected,
            relative_error=(amount-expected)/expected if amount is not None else None,
            outcome=classification))
    return findings

def row_matches(a,b):
    if len(a)!=len(b):return False
    for x,y in zip(a,b):
        if isinstance(x,int) and isinstance(y,int):
            if x!=y:return False
        elif isinstance(x,(float,int)) and isinstance(y,(float,int)):
            if abs(x-y)>0.000050000001:return False
        elif x!=y:return False
    return True

def result_matches(derived,recorded):
    if len(derived)!=len(recorded):return False
    unmatched=list(recorded)
    for row in derived:
        for i,other in enumerate(unmatched):
            if row_matches(row,other):
                unmatched.pop(i)
                break
        else:return False
    return not unmatched

def compare_references(archive,derived):
    cases=read_csv(archive/'test_suite_results.csv')
    evidence=[]
    for case in cases:
        cid=case['id']
        if case['expected_behavior']=='CLARIFY':
            alternatives={k:displayed_rows(v) for k,v in
                          (part.split(':',1) for part in case['interpretations'].split(' || '))}
            calc=derived['ambiguous_alternatives'][cid]
            ok=set(calc)==set(alternatives) and all(result_matches(calc[k],alternatives[k]) for k in calc)
            kind='alternatives only; clarification required'
        else:
            recorded=displayed_rows(case['gold_result'])
            if cid=='T8':
                # The archived rendering omits quotes around the vintage-year label.
                recorded=[(str(year),*rest) for year,*rest in recorded]
            ok=result_matches(derived['numeric_reference'][cid],recorded)
            kind='permitted sub-answer' if cid.startswith('X') else 'numeric reference'
        evidence.append(dict(id=cid,expected_action=case['expected_behavior'],evidence_type=kind,recorded_match=ok))
    assert set(r['id'] for r in evidence)==set(CASE_IDS)
    return evidence
