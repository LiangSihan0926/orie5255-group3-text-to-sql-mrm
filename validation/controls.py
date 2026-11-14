"""Bounded T4 experiments. Archived SQL is fingerprinted as text and never executed."""
from dataclasses import dataclass
import re
import sqlite3
from .audit import runtime_ok

@dataclass(frozen=True)
class Contract:
    cohort: str
    grain: str
    measure: str
    unit: str
    cutoff: str | None

T4 = Contract('account has a card withdrawal','loan','approved amount','source units',None)
IN = """SELECT SUM(l.amount) AS total_approved_loan_amount
        FROM loan l WHERE l.account_id IN (
        SELECT DISTINCT t.account_id FROM trans t WHERE t.operation = 'VYBER KARTOU')"""
EXISTS = """SELECT SUM(l.amount) FROM loan l WHERE EXISTS (
        SELECT 1 FROM trans t WHERE t.account_id = l.account_id AND t.operation = 'VYBER KARTOU')"""
# No arbitrary SQL is executed by the proposed gate. The token comparison is limited
# to two independently reviewed SQL texts; a production implementation would use
# a typed plan and a trusted parameterized compiler.
TOKEN = re.compile(r"'(?:[^']|'')*'|[A-Za-z_][A-Za-z_0-9]*|[0-9]+|[().,;=]|\S")
def fingerprint(s):
    tokens=TOKEN.findall(s)
    if tokens and tokens[-1]==';':
        tokens.pop()
    return tuple(t if t.startswith("'") else t.casefold() for t in tokens)

APPROVED=frozenset(fingerprint(s) for s in (IN,EXISTS))

def accepted(sql, contract=T4):
    return contract==T4 and fingerprint(sql) in APPROVED

def replay_t4(rows):
    out=[]
    for r in rows:
        if r['repair']!='on' or r['id']!='T4':continue
        base=runtime_ok(r) and r['action']=='answer'
        gate=base and accepted(r['sql'])
        out.append(dict(model=r['model'],prompt=r['condition'],repeat=int(r['run']),
                        attempts=int(r['attempts']),base_release_proxy=base,
                        matched_key_result=r['result_match']=='True',
                        candidate_recognized=accepted(r['sql']),gated_release_proxy=gate))
    return out

# Deterministically constructed, read-only financial candidates for small synthetic fixtures.
# Correct variants show the cost of a conservative gate; incorrect ones emulate statistical
# or relational calculation mistakes, not access-control exploits.
CANDIDATES=(
    ('approved_in',True,IN),
    ('approved_exists',True,EXISTS),
    ('equivalent_grouped_join',True,"""SELECT SUM(l.amount) FROM loan l JOIN (
        SELECT account_id FROM trans WHERE operation='VYBER KARTOU' GROUP BY account_id
        ) e ON l.account_id=e.account_id"""),
    ('equivalent_aliases',True,EXISTS.replace('loan l','loan AS loan_row').replace('l.','loan_row.')),
    ('transaction_fanout',False,"""SELECT SUM(l.amount) FROM loan l JOIN trans t
        ON l.account_id=t.account_id WHERE t.operation='VYBER KARTOU'"""),
    ('constant_answer',False,'SELECT 100'),
    ('holding_card_proxy',False,'SELECT SUM(l.amount) FROM loan l JOIN card c ON l.account_id=c.account_id'),
    ('dedup_by_amount',False,EXISTS.replace('SUM(l.amount)','SUM(DISTINCT l.amount)')),
    ('loan_count',False,EXISTS.replace('SUM(l.amount)','COUNT(*)')),
)

SCENARIOS={'base':100,'extra_event_A':100,'first_event_B':300,'same_amount_C':200}

def fixture(which):
    con=sqlite3.connect(':memory:')
    con.executescript("""
      CREATE TABLE loan(loan_id INTEGER PRIMARY KEY,account_id INTEGER,amount INTEGER);
      CREATE TABLE trans(trans_id INTEGER PRIMARY KEY,account_id INTEGER,operation TEXT);
      CREATE TABLE card(account_id INTEGER PRIMARY KEY);
      INSERT INTO loan VALUES(1,1,100),(2,2,200);
      INSERT INTO trans VALUES(1,1,'VYBER KARTOU'),(2,2,'OTHER');
      INSERT INTO card VALUES(1),(2);
    """)
    if which=='extra_event_A':
        con.execute("INSERT INTO trans VALUES(3,1,'VYBER KARTOU')")
    elif which=='first_event_B':
        con.execute("INSERT INTO trans VALUES(3,2,'VYBER KARTOU')")
    elif which=='same_amount_C':
        con.execute('INSERT INTO loan VALUES(3,3,100)')
        con.execute("INSERT INTO trans VALUES(3,3,'VYBER KARTOU')")
    con.execute('PRAGMA query_only=ON')
    return con

def fixtures():
    report=[]
    for cid,correct,sql in CANDIDATES:
        actual={}
        for scenario in SCENARIOS:
            con=fixture(scenario)
            try: actual[scenario]=con.execute(sql).fetchone()[0]
            finally: con.close()
        report.append(dict(candidate=cid,semantically_correct=correct,gate_accepts=accepted(sql),
                           amounts=actual,passes_base=actual['base']==100,
                           passes_two_proposed_variants=all(actual[k]==SCENARIOS[k] for k in ('base','extra_event_A','first_event_B')),
                           passes_all=actual==SCENARIOS))
    return report
