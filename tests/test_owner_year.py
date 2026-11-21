"""Regression cases for distinct owners and origination-year means."""

import sqlite3
import unittest

from validation import owner_year, reference, shadow, shadow_score


def contract(metric, **fields):
    return {'metric': metric, 'as_of': reference.AS_OF, 'snapshot_sha256': reference.SNAPSHOT_SHA, **fields}


class OwnerYearTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        context = shadow.open_shadow()
        cls.snapshot = context.__enter__()
        cls.addClassCleanup(context.__exit__, None, None, None)

    def fixture(self):
        con = sqlite3.connect(':memory:')
        self.addCleanup(con.close)
        con.executescript("""
            CREATE TABLE loan(loan_id INTEGER PRIMARY KEY, account_id INTEGER, date TEXT, amount INTEGER);
            CREATE TABLE disp(account_id INTEGER, client_id INTEGER, type TEXT);
        """)
        return con

    def test_snapshot_owners_and_account_coverage(self):
        output = shadow.evaluate(self.snapshot, contract(owner_year.OWNERS))
        self.assertEqual(output['action'], 'answer')
        self.assertTrue(shadow_score.answer_has_disclosures(output))
        self.assertEqual((output['value'], output['unit']), (682, 'clients'))
        self.assertEqual(output['evidence'], {'borrowing_account_count': 682, 'loan_count': 682})
        self.assertNotIn('client_id', output['evidence'])

    def test_distinct_owners_across_repeated_loans_and_shared_ownership(self):
        con = self.fixture()
        con.executescript("""
            INSERT INTO loan VALUES (1,10,'1997-03-01',100), (2,10,'1997-06-01',100),
                                    (3,20,'1998-02-01',200), (4,30,'1998-03-01',300);
            INSERT INTO disp VALUES (10,1,'OWNER'), (10,8,'DISPONENT'), (20,1,'OWNER'),
                                    (20,1,'OWNER'), (30,1,'OWNER'), (30,2,'OWNER'), (40,3,'OWNER');
        """)
        session = shadow._Session(con, shadow.MAX_SECONDS)
        reply = shadow.evaluate(session, contract(owner_year.OWNERS))
        self.assertEqual(reply['value'], 2)
        self.assertEqual(reply['evidence'], {'borrowing_account_count': 3, 'loan_count': 4})

    def test_missing_owner_holds_but_an_empty_portfolio_has_zero_owners(self):
        con = self.fixture()
        session = shadow._Session(con, shadow.MAX_SECONDS)
        reply = shadow.evaluate(session, contract(owner_year.OWNERS))
        self.assertEqual((reply['value'], reply['evidence']), (0, {'borrowing_account_count': 0, 'loan_count': 0}))
        incomplete = self.fixture()
        incomplete.executescript("INSERT INTO loan VALUES (1,10,'1997-01-01',100); "
                                 "INSERT INTO disp VALUES (10,1,'DISPONENT');")
        held = shadow.evaluate(shadow._Session(incomplete, shadow.MAX_SECONDS), contract(owner_year.OWNERS))
        self.assertEqual(held['reason'], 'unreconciled')

    def test_snapshot_mean_reconciles_for_each_supported_year(self):
        # Independent totals from individual dated loan records on the pinned snapshot.
        years = {1993: (20, 2619276), 1994: (101, 13379904), 1995: (90, 13344372),
                 1996: (117, 18317676), 1997: (196, 30731364), 1998: (158, 24869148)}
        profile = shadow.evaluate(self.snapshot, contract(owner_year.YEAR_PROFILE))
        self.assertEqual(set(profile['value']), {str(year) for year in years})
        self.assertEqual(profile['evidence'], {'loan_count': 682, 'approved_amount_sum': 103261740,
                                               'first_year': 1993, 'last_year': 1998, 'years_with_loans': 6,
                                               'years_without_loans': []})
        self.assertTrue(shadow_score.answer_has_disclosures(profile))
        for year, (count, principal) in years.items():
            with self.subTest(year=year):
                reply = shadow.evaluate(self.snapshot, contract(owner_year.YEAR_MEAN, origination_year=year))
                self.assertEqual(reply['action'], 'answer')
                self.assertEqual((reply['value'], reply['unit']), (principal / count, 'source_units'))
                self.assertEqual(profile['value'][str(year)],
                                 {'loan_count': count, 'approved_amount_sum': principal, 'mean': principal / count})
                self.assertTrue(shadow_score.answer_has_disclosures(reply))
                self.assertEqual(reply['evidence'], {'loan_count': count, 'approved_amount_sum': principal,
                                                     'origination_year': year})
                self.assertEqual(reply['parameters'], {'start': f'{year}-01-01', 'stop': f'{year+1}-01-01'})

    def test_year_boundaries_equal_amounts_empty_cohort_and_real_zero(self):
        con = self.fixture()
        con.executescript("""
            INSERT INTO loan VALUES (1,10,'1996-12-31',900), (2,10,'1997-01-01',120),
                                    (3,10,'1997-08-01',120), (4,20,'1997-12-31',300),
                                    (5,20,'1998-01-01',0);
        """)
        session = shadow._Session(con, shadow.MAX_SECONDS)
        selected = shadow.evaluate(session, contract(owner_year.YEAR_MEAN, origination_year=1997))
        self.assertEqual(selected['value'], 180)
        self.assertEqual(selected['evidence'], {'loan_count': 3, 'approved_amount_sum': 540, 'origination_year': 1997})
        zero = shadow.evaluate(session, contract(owner_year.YEAR_MEAN, origination_year=1998))
        self.assertEqual((zero['value'], zero['evidence']['loan_count']), (0, 1))
        self.assertEqual(shadow.evaluate(session, contract(owner_year.YEAR_MEAN,
                                                          origination_year=1995))['reason'], 'undefined_mean')
        profile = shadow.evaluate(session, contract(owner_year.YEAR_PROFILE))
        self.assertEqual(profile['evidence']['years_without_loans'], [1993, 1994, 1995])
        self.assertEqual(set(profile['value']), {'1996', '1997', '1998'})
        self.assertEqual(profile['value']['1998']['mean'], 0)
        empty_session = shadow._Session(self.fixture(), shadow.MAX_SECONDS)
        self.assertEqual(shadow.evaluate(empty_session, contract(owner_year.YEAR_PROFILE))['reason'], 'undefined_mean')

    def test_year_scope_is_explicit_typed_and_within_the_observed_period(self):
        for fields in [{}, {'origination_year': 1992}, {'origination_year': 1999}, {'origination_year': 2025},
                       {'origination_year': '1997'}, {'origination_year': 1997.0}, {'origination_year': True}]:
            with self.subTest(fields=fields):
                self.assertEqual(shadow.evaluate(self.snapshot, contract(owner_year.YEAR_MEAN, **fields))['reason'],
                                 'invalid_scope')
        self.assertEqual(shadow.evaluate(self.snapshot, contract(owner_year.OWNERS,
                                                                  origination_year=1997))['reason'], 'unsupported_scope')
