"""Check each loan against its account's first recorded qualifying event."""
import sqlite3
import unittest

from report.scripts.audit_withdrawal_timing import measure


class WithdrawalTimingTests(unittest.TestCase):
    def test_repeated_events_multiple_loans_and_approval_date_boundaries(self):
        con = sqlite3.connect(':memory:')
        self.addCleanup(con.close)
        con.executescript("""
            CREATE TABLE loan(account_id INTEGER, date TEXT, amount INTEGER);
            CREATE TABLE trans(account_id INTEGER, date TEXT, operation TEXT);
            INSERT INTO loan VALUES (1,'1997-01-01',100), (1,'1997-02-01',100), (1,'1997-03-01',110),
                                    (2,'1997-04-01',90), (3,'1999-01-01',200);
            INSERT INTO trans VALUES (1,'1996-01-01','VKLAD'), (1,'1997-02-01','VYBER KARTOU'),
                                     (1,'1997-03-01','VYBER KARTOU'), (2,'1999-01-01','VYBER KARTOU');
        """)
        output = measure(con, '1998-12-31')
        amounts = {'before_approval': 110, 'on_approval_date': 100, 'after_approval': 100,
                   'no_recorded_withdrawal': 90}
        for group, total in amounts.items():
            self.assertEqual(output[group], {'loans': 1, 'approved_principal_source_units': total})
