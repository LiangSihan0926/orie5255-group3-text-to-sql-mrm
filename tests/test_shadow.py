import gzip
import sqlite3
from datetime import date
import tempfile
import unittest
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from runpy import run_path
from unittest.mock import patch

from validation import cohorts, questions, reference, shadow


def request(metric, cutoff=reference.AS_OF, **fields):
    return dict(metric=metric, as_of=cutoff, snapshot_sha256=reference.SNAPSHOT_SHA, **fields)


class ShadowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.context = shadow.open_shadow()
        cls.session = cls.context.__enter__()
        cls.addClassCleanup(cls.context.__exit__, None, None, None)

    def test_reconciled_amounts_preserve_loan_grain_and_units(self):
        cases = [('withdrawal_loan_amount', 23120268, 148), ('approved_loan_total', 103261740, 682)]
        for measure, amount, count in cases:
            with self.subTest(metric=measure):
                with patch('validation.shadow.monotonic', return_value=1.0):
                    result = shadow.evaluate(self.session, request(measure))
                self.assertEqual(result['action'], 'answer')
                self.assertEqual((result['value'], result['evidence']['loan_count']), (amount, count))
                self.assertEqual(result['unit'], 'source_units')
                self.assertEqual(result['role'], shadow.ROLE)
                self.assertIn('exchange rate', result['caveat'])
                self.assertEqual(sha256(result['sql'].encode()).hexdigest(), result['template_sha256'])

    def test_cash_and_contract_count_distress_proxies_use_their_own_denominators(self):
        expected = {'distressed_loan_share': (76, 682),
                    'distressed_approved_amount_share': (15580152, 103261740),
                    'finished_unpaid_share': (31, 234), 'running_delinquent_share': (45, 448)}
        for metric, (numerator, denominator) in expected.items():
            with self.subTest(metric=metric):
                answer = shadow.evaluate(self.session, request(metric))
                self.assertEqual(answer['evidence'], {'numerator': numerator, 'denominator': denominator})
                self.assertEqual(answer['value'], numerator / denominator)
                self.assertEqual(answer['unit'], 'fraction')

    def test_historical_schedule_keeps_valid_zero(self):
        for cutoff, expected in [('1993-01-01', 0), ('1996-12-31', 247)]:
            with self.subTest(cutoff=cutoff):
                answer = shadow.evaluate(self.session, request('scheduled_active_loans', cutoff))
                self.assertEqual(answer['value'], expected)
                self.assertEqual(answer['parameters'], {'as_of': cutoff})
                self.assertIn('scheduled', answer['caveat'].lower())

    def test_unemployment_weights_exclude_missing_districts(self):
        for mode, denom, numerator in [('loan_count', 674, 191560),
                                       ('approved_amount', 101323308, 28086567720)]:
            with self.subTest(weight=mode):
                result = shadow.evaluate(self.session, request('district_unemployment_1995_by_' + mode))
                self.assertEqual(result['evidence'], {'weight_sum': denom,
                    'weighted_rate_basis_points_sum': numerator, 'included_loans': 674, 'excluded_loans': 8})
                self.assertEqual(result['unit'], 'percent')
                self.assertAlmostEqual(result['value'], numerator / denom / 100)

    def test_vintage_results_disclose_follow_up(self):
        for year, originated, finished, unpaid, distressed in [(1994, 101, 85, 12, 14), (1997, 196, 43, 3, 26)]:
            for metric, n, denom in [('vintage_finished_unpaid_share', unpaid, finished),
                                     ('vintage_distressed_loan_share', distressed, originated)]:
                with self.subTest(year=year, metric=metric):
                    answer = shadow.evaluate(self.session, request(metric, vintage=year))
                    self.assertEqual(answer['evidence'], {'vintage': year, 'originated_loans': originated,
                        'finished_loans': finished, 'numerator': n, 'denominator': denom})
                    self.assertEqual(answer['value'], n / denom)

    def test_booking_region_owner_residence_and_owner_gender_have_distinct_cohorts(self):
        for key, population, distressed in [(cohorts.MORAVIA, 246, 31), (cohorts.PRAGUE_OWNER, 79, 6)]:
            with self.subTest(metric=key):
                output = shadow.evaluate(self.session, request(key))
                self.assertEqual(output['value'], distressed / population)
                self.assertEqual(output['evidence'], {'numerator': distressed, 'denominator': population})
        output = shadow.evaluate(self.session, request(cohorts.FEMALE_OWNER))
        self.assertAlmostEqual(output['value'], 53996160 / 348)
        self.assertEqual(output['evidence'], {'loan_count': 348, 'approved_amount_sum': 53996160})

    def test_last_balance_checks_quiet_accounts_and_same_day_ties(self):
        # The independent calculation must look back before December for a dormant account.
        db = sqlite3.connect(':memory:')
        self.addCleanup(db.close)
        db.executescript("""
            CREATE TABLE account(account_id INTEGER PRIMARY KEY);
            CREATE TABLE trans(trans_id INTEGER PRIMARY KEY, account_id INTEGER, date TEXT, balance INTEGER);
            INSERT INTO account VALUES (1), (2), (3);
            INSERT INTO trans VALUES (1,1,'1998-12-20',70), (4,1,'1998-12-20',90),
                                     (2,2,'1996-01-01',-30), (5,2,'1999-01-01',999),
                                     (3,3,'1998-12-31',0);
        """)
        cutoff = date.fromisoformat(reference.AS_OF)
        key = cohorts.CLOSING_BALANCE
        spec = cohorts.catalog(shadow.Metric, shadow.SOURCE_CURRENCY)[key]
        observed = db.execute(spec.sql, {'as_of': cutoff.isoformat()}).fetchone()
        self.assertEqual(observed, (3, 60, 1, 1, 1, 90, -30, 0))
        self.assertEqual(observed, cohorts.base_counts(db, key, cutoff))
        self.assertEqual(cohorts.render(key, observed), (60, {
            'account_count': 3, 'positive_account_count': 1, 'negative_account_count': 1,
            'zero_account_count': 1, 'positive_balance_sum': 90, 'negative_balance_sum': -30,
            'zero_balance_sum': 0}))
        db.execute('INSERT INTO account VALUES (4)')
        with self.assertRaisesRegex(ValueError, 'lacks an observable balance'):
            cohorts.base_counts(db, key, cutoff)

    def test_only_the_three_reviewed_mixed_wordings_receive_aggregate_parts(self):
        suite = Path(__file__).resolve().parents[1] / 'archive' / 'text2sql_bird' / 'test_suite.py'
        cases = {case['id']: case['question'] for case in run_path(str(suite))['CASES'] if case['id'].startswith('X')}
        trace = []
        self.session.connection.set_trace_callback(trace.append)
        try:
            for cid in ('X1', 'X2', 'X3'):
                original = cases[cid]
                result = questions.answer_question(self.session, original)
                self.assertEqual(result['action'], 'partial')
                self.assertTrue(result['review_required'])
                self.assertIn('refused', result['explanation'])
                self.assertIn('withheld_action', result)
                permitted = result['permitted_answer']
                if cid == 'X1':
                    self.assertEqual(result['withheld_action'], 'individual_birth_dates_and_loan_amounts')
                    self.assertEqual(permitted['metric'], cohorts.AGE_BANDS)
                    self.assertEqual(permitted['unit'], 'loans_and_source_units')
                    self.assertEqual(permitted['value'], {
                        '<30': {'loan_count': 13, 'approved_amount': 3543024},
                        '30-49': {'loan_count': 21, 'approved_amount': 5292288},
                        '50+': {'loan_count': 11, 'approved_amount': 2382492}})
                    self.assertEqual(permitted['evidence'], {'total_loans': 45})
                    self.assertTrue(all('substr(' in stmt for stmt in trace if 'birth_date' in stmt))
                elif cid == 'X2':
                    self.assertEqual(permitted['evidence'], {'numerator': 76, 'denominator': 682})
                else:
                    self.assertEqual(permitted['value'], {'12': 131, '24': 138, '36': 130, '48': 138, '60': 145})
                    self.assertEqual(permitted['evidence']['loan_count'], sum(permitted['value'].values()))
                self.assertTrue(trace and all(statement.lstrip().upper().startswith('SELECT') for statement in trace))
                trace.clear()
                for changed in [original + ' ', original.swapcase(), original + ' Please also list the loan amounts.']:
                    self.assertEqual(questions.answer_question(self.session, changed)['action'], 'hold')
                self.assertEqual(questions.answer_question(self.session, original, role='unassigned')['action'], 'hold')
                self.assertEqual(trace, [])
        finally:
            self.session.connection.set_trace_callback(None)

    def test_age_bands_reject_unverifiable_and_single_owner_groups(self):
        db = sqlite3.connect(':memory:')
        self.addCleanup(db.close)
        db.executescript("""
            CREATE TABLE disp(account_id INTEGER, client_id INTEGER, type TEXT);
            CREATE TABLE client(client_id INTEGER, birth_date TEXT);
            CREATE TABLE loan(account_id INTEGER, amount INTEGER, status TEXT);
            INSERT INTO client VALUES (1,'1968-12-31'), (2,'1949-01-01'), (3,'1948-06-30');
            INSERT INTO disp VALUES (11,1,'OWNER'), (12,2,'OWNER'), (12,3,'DISPONENT'), (13,3,'OWNER');
            INSERT INTO loan VALUES (11,100,'D'), (12,200,'D'), (13,300,'C');
        """)
        key = cohorts.AGE_BANDS
        mask = shadow._Session(db, 2)
        result = shadow.evaluate(mask, request(key))
        self.assertEqual(result['value']['30-49'], {'loan_count': 2, 'approved_amount': 300})
        self.assertEqual(result['value']['50+'], {'loan_count': 0, 'approved_amount': 0})
        db.set_authorizer(lambda *_: sqlite3.SQLITE_OK)
        db.execute("UPDATE loan SET status='D' WHERE account_id=13")
        self.assertEqual(shadow.evaluate(mask, request(key))['reason'], 'unreconciled')
        db.set_authorizer(lambda *_: sqlite3.SQLITE_OK)
        db.execute("UPDATE client SET birth_date=NULL WHERE client_id=3")
        result = shadow.evaluate(mask, request(key))
        self.assertEqual((result['action'], result['reason']), ('hold', 'unreconciled'))
        self.assertNotIn('value', result)

    def test_contract_errors_hold_before_a_query_runs(self):
        cases = [
            ({}, {}, 'missing_contract'),
            (request('approved_loan_total'), {'role': 'unassigned'}, 'unauthorized_role'),
            (dict(request('approved_loan_total'), snapshot_sha256='other'), {}, 'snapshot_mismatch'),
            (request('approved_loan_total', '1997-12-31'), {}, 'snapshot_only'),
            (request('approved_loan_total', unit='USD'), {}, 'unsupported_unit'),
            (request('approved_loan_total', output_detail='by loan'), {}, 'unsupported_request'),
            (request('approved_loan_total', vintage=1994), {}, 'unsupported_scope'),
            (request(cohorts.AGE_BANDS, '1997-12-31'), {}, 'snapshot_only'),
            (request(cohorts.AGE_BANDS, output_detail='by owner'), {}, 'unsupported_request'),
            (request('scheduled_active_loans', '1995-02-29'), {}, 'invalid_cutoff'),
            (request('scheduled_active_loans', '2000-01-01'), {}, 'invalid_cutoff'),
            (request('scheduled_active_loans', '19961231'), {}, 'invalid_cutoff'),
            (request('T7'), {}, 'unknown_metric'), (request('T8'), {}, 'unknown_metric'),
            (request('vintage_finished_unpaid_share'), {}, 'invalid_vintage'),
            (request('vintage_distressed_loan_share', vintage='1994'), {}, 'invalid_vintage'),
        ]
        trace = []
        self.session.connection.set_trace_callback(trace.append)
        try:
            for payload, trusted_context, reason in cases:
                with self.subTest(payload=payload, trusted_context=trusted_context):
                    result = shadow.evaluate(self.session, payload, **trusted_context)
                    self.assertEqual((result['action'], result['reason']), ('hold', reason))
                    self.assertNotIn('value', result)
            self.assertEqual(trace, [])
        finally:
            self.session.connection.set_trace_callback(None)

    def test_catalog_faults_cannot_emit_a_plausible_wrong_answer(self):
        name = 'approved_loan_total'
        # Simulate accidental internal template edits. Each test still uses safe aggregates.
        for sql, reason in [
            ('SELECT COUNT(*), SUM(amount) + 1 FROM loan', 'unreconciled'),
            ('SELECT COUNT(*), SUM(amount) FROM loan GROUP BY amount > 50000', 'output_grain'),
            ('SELECT COUNT(*), SUM(amount) FROM loan WHERE duration > 0', 'execution_failed'),
        ]:
            with self.subTest(reason=reason):
                bad = replace(shadow.CATALOG[name], sql=sql)
                with patch.dict(shadow.CATALOG, {name: bad}):
                    result = shadow.evaluate(self.session, request(name))
                self.assertEqual((result['action'], result['reason']), ('hold', reason))
                self.assertNotIn('value', result)
                self.assertEqual(shadow.evaluate(self.session, request(name))['action'], 'answer')

    def test_timeout_emits_no_partial_result(self):
        short = replace(self.session, seconds=1e-9)
        result = shadow.evaluate(short, request(cohorts.CLOSING_BALANCE))
        self.assertEqual((result['action'], result['reason']), ('hold', 'timeout'))
        self.assertNotIn('value', result)
        # The interrupted statement must not poison subsequent requests on the same connection.
        next_request = shadow.evaluate(self.session, request('approved_loan_total'))
        self.assertEqual(next_request['value'], 103261740)

    def test_activation_checks_actual_database_identity(self):
        with tempfile.TemporaryDirectory() as folder:
            other = Path(folder) / 'other.sqlite.gz'
            other.write_bytes(gzip.compress(b'different snapshot'))
            with self.assertRaisesRegex(ValueError, 'does not match'):
                with shadow.open_shadow(other):
                    self.fail('Opened the wrong data source')


if __name__ == '__main__':
    unittest.main()
