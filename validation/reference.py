"""Rederive the reference outcomes from base tables, without running the reference SQL."""
from collections import Counter, defaultdict
from contextlib import contextmanager
from datetime import date, timedelta
from hashlib import sha256
from math import fsum
from pathlib import Path
from tempfile import TemporaryDirectory
import gzip
import shutil
import sqlite3

SNAPSHOT_SHA = 'd15d89cdb068a202b6f2b99342af44dffc1d52545b39ceaf62efdc0ba570101e'
AS_OF = '1998-12-31'
BAD = {'B', 'D'}
FINISHED = {'A', 'B'}

@contextmanager
def snapshot(compressed, db=None):
    """Check the raw bytes before opening an immutable read-only connection."""
    with TemporaryDirectory(prefix='bird-reference-') as tmp:
        if db is None:
            db = Path(tmp) / 'financial.sqlite'
            with gzip.open(compressed, 'rb') as src, db.open('wb') as dest:
                shutil.copyfileobj(src, dest)
        db = Path(db).resolve()
        with db.open('rb') as f:
            observed = sha256()
            for block in iter(lambda: f.read(1 << 20), b''):
                observed.update(block)
        if observed.hexdigest() != SNAPSHOT_SHA:
            raise ValueError('The supplied database does not match the pilot snapshot')
        con = sqlite3.connect(db.as_uri()+'?mode=ro&immutable=1', uri=True)
        try:
            con.execute('PRAGMA query_only=ON')
            con.execute('PRAGMA trusted_schema=OFF')
            yield con
        finally:
            con.close()

def month_end(start, duration):
    # Match the recorded SQLite month-overflow convention. Do not infer actual repayment.
    d = date.fromisoformat(start)
    y, m = divmod(d.year*12+d.month-1+duration, 12)
    return date(y, m+1, 1) + timedelta(days=d.day-1)

def grouped(loans, key):
    out = defaultdict(list)
    for row in loans:
        out[key(row)].append(row)
    return out

def ratio(loans, statuses=BAD, weight=False):
    w = (lambda row: row[2]) if weight else (lambda row: 1)
    denom = sum(map(w,loans))
    return sum(w(row) for row in loans if row[4] in statuses)/denom if denom else None

def mean(items):
    seq = list(items)
    return sum(seq)/len(seq) if seq else None

def top(loans, grouping, statuses=BAD, weight=False):
    ranked = sorted(((-ratio(rows,statuses,weight),region)
                     for region,rows in grouped(loans,grouping).items()))
    score, region = ranked[0]
    return [(region, -score)]

def recompute(con):
    loans = list(con.execute('SELECT loan_id, account_id, amount, date, status, duration FROM loan'))
    account_district = dict(con.execute('SELECT account_id,district_id FROM account'))
    district = {key:(region,unemp) for key,region,unemp in
                con.execute('SELECT district_id,A3,A12 FROM district')}
    # Read only the year required for the approved age-band reference; emit no row-level data.
    client = {key:(gender,did,birthyear) for key,gender,did,birthyear in
              con.execute('SELECT client_id,gender,district_id,substr(birth_date,1,4) FROM client')}
    roles = list(con.execute('SELECT account_id,client_id,type FROM disp'))
    owner = {account:c for account,c,role in roles if role=='OWNER'}
    assert len(owner)==sum(r=='OWNER' for _,_,r in roles)
    assert len({l[0] for l in loans})==len(loans)
    branch = lambda row: district[account_district[row[1]]][0]
    residence = lambda row: district[client[owner[row[1]]][1]][0]

    # Scan source columns once. The benchmark transaction tables are never joined by the validator.
    withdrawal = Counter()
    latest_hi, latest_lo = {}, {}
    trans_count = 0
    for aid, day, tid, operation, balance in con.execute(
        'SELECT account_id,date,trans_id,operation,balance FROM trans'
    ):
        trans_count+=1
        if operation=='VYBER KARTOU':
            withdrawal[aid]+=1
        if day<=AS_OF:
            high=(day,tid); low=(day,-tid)
            if aid not in latest_hi or high>latest_hi[aid][0]:
                latest_hi[aid]=(high,balance)
            if aid not in latest_lo or low>latest_lo[aid][0]:
                latest_lo[aid]=(low,balance)

    sixty=[l[2] for l in loans if l[5]==60]
    moravia=[l for l in loans if branch(l) in ('north Moravia','south Moravia')]
    women=[l[2] for l in loans if client[owner[l[1]]][0]=='F']
    eligible=[l for l in loans if withdrawal[l[1]]]
    prague=[l for l in loans if residence(l)=='Prague']
    unemp=[district[account_district[l[1]]][1] for l in loans]
    unemp_amount=sum(loan[2] for loan,rate in zip(loans,unemp) if rate is not None)
    # Use the same compensated summation on all supported Python versions.
    observed_rates = [rate for rate in unemp if rate is not None]
    weighted_unemp = fsum(loan[2] * rate for loan, rate in zip(loans, unemp) if rate is not None)
    vintage=grouped(loans,lambda l:l[3][:4])
    t8=[]
    vintage_sensitivity=[]
    for year in ('1994','1997'):
        group=vintage[year]
        finished=[l for l in group if l[4] in FINISHED]
        t8.append((year,len(group),len(finished),ratio(finished,{'B'}),ratio(group)))
        vintage_sensitivity.append(dict(year=year,originated_loans=len(group),finished_loans=len(finished),
            finished_status_b=sum(loan[4]=='B' for loan in finished),
            finished_share=len(finished)/len(group),finished_b_count_share=ratio(finished,{'B'}),
            all_bd_count_share=ratio(group),
            finished_b_approved_amount_share=ratio(finished,{'B'},weight=True)))
    bands=defaultdict(list)
    for l in loans:
        if l[4]=='D':
            age=1998-int(client[owner[l[1]]][2])
            bands['<30' if age<30 else '30-49' if age<50 else '50+'].append(l[2])
    total=sum(l[2] for l in eligible)
    closing_balances = [balance for _, balance in latest_hi.values()]
    high = sum(closing_balances)
    balance_components = {
        'account_count': len(closing_balances),
        'positive_account_count': sum(balance > 0 for balance in closing_balances),
        'negative_account_count': sum(balance < 0 for balance in closing_balances),
        'zero_account_count': closing_balances.count(0),
        'positive_balance_sum': sum(balance for balance in closing_balances if balance > 0),
        'negative_balance_sum': sum(balance for balance in closing_balances if balance < 0),
        'zero_balance_sum': 0,
    }
    low=sum(x[1] for x in latest_lo.values())
    balance_changes=[abs(row[1]-latest_lo[account][1]) for account,row in latest_hi.items()]
    results={
        'E1': sorted(Counter(l[4] for l in loans).items()),
        'E2': [(sum(l[2] for l in vintage['1997']),)],
        'E3': [(mean(sixty),len(sixty))],
        'T1': [(ratio(loans, weight=True),)],
        'T2': [(ratio(moravia),)],
        'T3': [(mean(women),len(women))],
        'T4': [(total,len(eligible))],
        'T5': [(ratio(prague),len(prague))],
        'T6': [(sum(date.fromisoformat(l[3])<=date(1996,12,31)<month_end(l[3],l[5]) for l in loans),)],
        'T7': [(fsum(observed_rates) / len(observed_rates), unemp.count(None))],
        'T8': t8,
        'T9': [(high,)],
        'T10': [(sum(l[2] for l in loans),)],
        'X1': [(band,len(amounts),sum(amounts)) for band,amounts in sorted(bands.items())],
        'X2': [(ratio(loans),)],
        'X3': sorted(Counter(l[5] for l in loans).items()),
    }
    aids={l[1] for l in loans}
    ambiguous={
        'A1': {
            'B_only_count_branch': top(loans,branch,{'B'}),
            'BD_count_branch': top(loans,branch),
            'BD_amount_branch': top(loans,branch,weight=True),
            'BD_count_borrower': top(loans,residence),
        },
        'A2': {
            'accounts':[(len(aids),)],
            'owners':[(len({owner[a] for a in aids}),)],
            'all_clients':[(len({c for a,c,_ in roles if a in aids}),)],
        },
        'A3': {
            'relative_to_data_1998':[(mean(l[2] for l in vintage['1998']),)],
            # The observed archive used a current-date expression. Pin the illustrative 2025 prior year.
            'relative_to_today':[(mean(l[2] for l in vintage.get('2025',[])),)],
        }
    }
    male_links=[l[2] for l in loans for a,c,_ in roles
                if a==l[1] and client[c][0]=='M']
    male_owners=[l[2] for l in loans if client[owner[l[1]]][0]=='M']
    male_owner_vintage=grouped(
        (l for l in loans if client[owner[l[1]]][0]=='M'), lambda l:l[3][:4]
    )
    owner_1996, owner_1997 = (
        sum(l[2] for l in male_owner_vintage[year]) for year in ('1996','1997')
    )
    return {
        'raw_snapshot_sha256': SNAPSHOT_SHA,
        'rows':{'loans':len(loans),'transactions':trans_count},
        'numeric_reference': results,
        'english_replay_support': {
            'E1': {'loan_count': len(loans)},
            'E2': {'loan_count': len(vintage['1997']), 'origination_year': 1997},
            'E3': {'loan_count': len(sixty), 'approved_amount_sum': sum(sixty), 'duration_months': 60},
            'T1': {'numerator': sum(l[2] for l in loans if l[4] in BAD),
                   'denominator': sum(l[2] for l in loans)},
            'T2': {'numerator': sum(l[4] in BAD for l in moravia), 'denominator': len(moravia)},
            'T3': {'loan_count': len(women), 'approved_amount_sum': sum(women)},
            'T4': {'loan_count': len(eligible)},
            'T5': {'numerator': sum(l[4] in BAD for l in prague), 'denominator': len(prague)},
            'T9': balance_components,
            'T10': {'loan_count': len(loans)},
            'X1': {'total_loans': sum(len(amounts) for amounts in bands.values())},
            'X2': {'numerator': sum(l[4] in BAD for l in loans), 'denominator': len(loans)},
            'X3': {'loan_count': len(loans), 'duration_unit': 'months'},
        },
        'ambiguous_alternatives': ambiguous,
        'illustrations': {
            'T1_count_weighted': ratio(loans),
            'T4_transaction_fanout_total': sum(l[2]*withdrawal[l[1]] for l in eligible),
            'T4_transaction_join_rows': sum(withdrawal[l[1]] for l in eligible),
            'T6_snapshot_status_misused': sum(l[3]<='1996-12-31' and l[4] in ('C','D') for l in loans),
            'T7_weight_sensitivity': {
                'included_loans':len(unemp)-unemp.count(None),
                'excluded_loans':unemp.count(None),
                'approved_amount_denominator':unemp_amount,
                'count_weighted_percent':results['T7'][0][0],
                'amount_weighted_percent':weighted_unemp/unemp_amount,
            },
            'T8_vintage_sensitivity':vintage_sensitivity,
            'T9_alternative_tie_break': low,
            'T9_tie_break_absolute_difference': abs(high-low),
            'T9_tie_break_changed_accounts':sum(change>0 for change in balance_changes),
            'T9_tie_break_gross_absolute_change':sum(balance_changes),
            'Q132_all_authorized_links': {'rows':len(male_links),'average':mean(male_links)},
            'Q132_account_owners_only': {'rows':len(male_owners),'average':mean(male_owners)},
            'Q169_male_owner_growth': {
                'amount_1996':owner_1996, 'amount_1997':owner_1997,
                'growth_percent':100*(owner_1997-owner_1996)/owner_1996,
            },
        }
    }
