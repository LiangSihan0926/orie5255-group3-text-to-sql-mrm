"""Regional rankings for the pinned portfolio and controlled tie / coverage cases."""
from fractions import Fraction
import sqlite3
import unittest

from validation import regional, shadow
from validation.questions import answer_question
from validation.reference import AS_OF, SNAPSHOT_SHA


class RegionalRankingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        context = shadow.open_shadow()
        cls.session = context.__enter__()
        cls.addClassCleanup(context.__exit__, None, None, None)

    def test_all_english_contracts_rank_eight_regions_and_reconcile_portfolio(self):
        # These portfolio totals also distinguish B/all from B/finished and loan
        # counts from amounts. The runtime independently reconciles every region.
        portfolios = {
            ('distressed', 'count'): (76, 682), ('distressed', 'amount'): (15580152, 103261740),
            ('unpaid_all', 'count'): (31, 682), ('unpaid_all', 'amount'): (4362348, 103261740),
            ('finished_unpaid', 'count'): (31, 234), ('finished_unpaid', 'amount'): (4362348, 22965564),
        }
        for metric, (_, proxy, weight) in regional.CONTRACTS.items():
            with self.subTest(metric=metric):
                question = regional.QUESTION_FORMS[metric][0] + '?'
                reply = answer_question(self.session, question)
                self.assertEqual((reply['action'], reply.get('metric')), ('answer', metric))
                value, support = reply['value'], reply['evidence']
                self.assertEqual(set(value), set(regional.REGIONS))
                self.assertEqual((support['region_count'], support['regions_ranked'],
                                  support['regions_without_denominator']), (8, 8, 0))
                self.assertEqual(support['eligible_loan_count'], 234 if proxy == 'finished_unpaid' else 682)
                self.assertEqual(support['loan_count'], 682)
                expected = portfolios[proxy, weight]
                self.assertEqual((support['total_numerator'], support['total_denominator']), expected)
                self.assertEqual(tuple(sum(row[k] for row in value.values())
                                       for k in ('numerator', 'denominator')), expected)
                rates = {region: Fraction(row['numerator'], row['denominator']) for region, row in value.items()}
                for region, row in value.items():
                    self.assertEqual(row['rank'], 1 + sum(r > rates[region] for r in rates.values()))
                    self.assertEqual(row['rate'], float(rates[region]))

    def test_weight_geography_and_status_population_change_the_result(self):
        examples = {
            'booking_distressed_rank_by_count': ('west Bohemia', 9, 57),
            'booking_distressed_rank_by_amount': ('north Moravia', 3871092, 18081312),
            'residence_distressed_rank_by_count': ('north Moravia', 19, 117),
            'booking_unpaid_all_rank_by_count': ('west Bohemia', 5, 57),
            'booking_finished_unpaid_rank_by_count': ('west Bohemia', 5, 22),
        }
        for metric, (winner, numerator, denominator) in examples.items():
            with self.subTest(metric=metric):
                request = {'metric': metric, 'snapshot_sha256': SNAPSHOT_SHA, 'as_of': AS_OF}
                reply = shadow.evaluate(self.session, request)
                self.assertEqual(reply['action'], 'answer')
                first = {region: row for region, row in reply['value'].items() if row['rank'] == 1}
                self.assertEqual(first, {winner: {'rank': 1, 'numerator': numerator,
                                                  'denominator': denominator, 'rate': numerator / denominator}})

    def test_ties_zero_rates_and_regions_without_eligible_loans(self):
        # Two regions tie at 1/2 from different integer counts. A third has
        # eligible loans with no bad status. A fourth has no finished loans.
        with sqlite3.connect(':memory:') as con:
            con.executescript("""
                CREATE TABLE district(district_id INTEGER, A3 TEXT);
                CREATE TABLE account(account_id INTEGER, district_id INTEGER);
                CREATE TABLE loan(account_id INTEGER, status TEXT);
                INSERT INTO district VALUES (1,'Prague'),(2,'east Bohemia'),(3,'west Bohemia'),(4,'south Moravia');
                INSERT INTO account VALUES (11,1),(12,2),(13,3),(14,4);
                INSERT INTO loan VALUES (11,'A'),(11,'B'),(12,'A'),(12,'A'),(12,'B'),(12,'B'),(13,'A'),(14,'C');
            """)
            metric = 'booking_finished_unpaid_rank_by_count'
            sql_counts = con.execute(regional.catalog(shadow.Metric)[metric].sql).fetchone()
            self.assertEqual(sql_counts, regional.base_counts(con, metric))
            ranked, support = regional.render(metric, sql_counts)
            self.assertEqual({region: row['rank'] for region, row in ranked.items()},
                             {'Prague': 1, 'east Bohemia': 1, 'west Bohemia': 3})
            self.assertEqual(ranked['west Bohemia']['rate'], 0)
            self.assertNotIn('south Moravia', ranked)
            self.assertEqual((support['loan_count'], support['eligible_loan_count'],
                              support['regions_without_denominator']), (8, 7, 5))
            con.execute("UPDATE loan SET status='C'")
            with self.assertRaises(ValueError):
                regional.render(metric, con.execute(regional.catalog(shadow.Metric)[metric].sql).fetchone())

    def test_owner_geography_does_not_silently_discard_or_duplicate_a_loan(self):
        with sqlite3.connect(':memory:') as con:
            con.executescript("""
                CREATE TABLE district(district_id INTEGER, A3 TEXT);
                CREATE TABLE client(client_id INTEGER, district_id INTEGER);
                CREATE TABLE disp(account_id INTEGER, client_id INTEGER, type TEXT);
                CREATE TABLE loan(account_id INTEGER, status TEXT);
                INSERT INTO district VALUES (1,'Prague');
                INSERT INTO client VALUES (1,1),(2,1);
                INSERT INTO loan VALUES (99,'B');
                INSERT INTO disp VALUES (99,1,'DISPONENT');
            """)
            metric = 'residence_distressed_rank_by_count'
            with self.assertRaises(KeyError):
                regional.base_counts(con, metric)
            con.execute("INSERT INTO disp VALUES (99,1,'OWNER')")
            self.assertEqual(regional.base_counts(con, metric)[-2:], (1, 1))
            con.execute("INSERT INTO disp VALUES (99,2,'OWNER')")
            with self.assertRaises(KeyError):
                regional.base_counts(con, metric)
