"""Synthetic ledgers exist only inside test temp directories, never as human-review evidence."""
import csv
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from validation.reference import AS_OF, SNAPSHOT_SHA
from validation.shadow import CATALOG, CATALOG_VERSION, ROLE, evaluate, open_shadow
from validation.shadow_score import answer_has_disclosures, capture, COLUMNS, INTAKE_COLUMNS, score_log


class ShadowScoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.originals = self.root / 'originals'
        self.ledger = self.root / 'review.csv'
        self.intake = self.root / 'intake.csv'

    def archive(self, action):
        candidate = self.root / 'reply.json'
        reply = {'action': action, 'reason': 'unit-test-fixture'}
        if action in {'answer', 'partial'}:
            sql = CATALOG['scheduled_active_loans'].sql
            answer = dict(action='answer', value=0, unit='loans', as_of='1993-01-01',
                          metric='scheduled_active_loans', role=ROLE, catalog_version=CATALOG_VERSION,
                          definition='test fixture', caveat='test fixture',
                          snapshot_date=AS_OF, snapshot_sha256=SNAPSHOT_SHA, sql=sql,
                          template_sha256=sha256(sql.encode()).hexdigest(), parameters={'as_of': '1993-01-01'},
                          evidence={'loan_count': 0})
            reply = answer if action == 'answer' else dict(action='partial', permitted_answer=answer)
        candidate.write_text(json.dumps(reply))
        return capture(candidate, self.originals)

    def rows(self, answers=30, holds=0, seconds=600):
        answer = self.archive('answer')
        hold = self.archive('hold')
        return [dict(zip(COLUMNS, (
            str(seq), f'test-only-{seq}', 'true', 'true', digest, digest,
            'test-fixture', str(seconds), 'true' if action == 'answer' else '',
            'true' if action == 'answer' else '', 'false', 'false',
        ))) for seq, (action, digest) in enumerate([('answer', answer)] * answers + [('hold', hold)] * holds, 1)]

    def write_csv(self, path, rows, fields):
        with path.open('w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(rows)

    def grade(self, rows, source=None):
        self.write_csv(self.ledger, rows, COLUMNS)
        self.write_csv(self.intake, rows if source is None else source, INTAKE_COLUMNS)
        return score_log(self.ledger, self.originals, self.intake)

    def test_new_portfolio_receipts_validate_the_reported_numbers_and_revision(self):
        def latest(session, metric, **fields):
            return evaluate(session, dict(metric=metric, as_of=AS_OF, snapshot_sha256=SNAPSHOT_SHA, **fields))

        with open_shadow() as session:
            historic = latest(session, 'approved_loan_total')
            self.assertTrue(answer_has_disclosures(dict(historic, catalog_version='financial-aggregates-v1')))
            ranking = latest(session, 'booking_distressed_rank_by_count')
            self.assertTrue(answer_has_disclosures(ranking))
            self.assertFalse(answer_has_disclosures(dict(ranking, catalog_version='financial-aggregates-v1')))
            changed = dict(ranking['value'])
            changed['west Bohemia'] = dict(changed['west Bohemia'], rank=2)
            self.assertFalse(answer_has_disclosures(dict(ranking, value=changed)))
            wrong_count = dict(ranking['evidence'], eligible_loan_count=1)
            self.assertFalse(answer_has_disclosures(dict(ranking, evidence=wrong_count)))
            mean = latest(session, 'mean_approved_amount_by_year', origination_year=1997)
            self.assertFalse(answer_has_disclosures(dict(mean, value=mean['value'] * 2)))
            profile = latest(session, 'mean_approved_amount_by_origination_year')
            missing = dict(profile['value'])
            missing.pop('1997')
            self.assertFalse(answer_has_disclosures(dict(profile, value=missing)))

    def test_net_balance_receipts_use_the_sql_and_support_for_their_catalog_version(self):
        with open_shadow() as session:
            new = evaluate(session, dict(metric='closing_deposit_balance', as_of=AS_OF, snapshot_sha256=SNAPSHOT_SHA))
        self.assertTrue(answer_has_disclosures(new))
        legacy_sql = '''SELECT COUNT(*), SUM(balance) FROM (
                   SELECT balance, ROW_NUMBER() OVER (
                       PARTITION BY account_id ORDER BY date DESC, trans_id DESC
                   ) AS closing_rank
                   FROM trans
                   WHERE date <= :as_of AND (
                       date >= date(:as_of, 'start of month') OR account_id IN (
                           SELECT account_id FROM account
                           EXCEPT SELECT account_id FROM trans
                                  WHERE date BETWEEN date(:as_of, 'start of month') AND :as_of
                       )
                   )
               ) WHERE closing_rank = 1'''
        old = dict(new, sql=legacy_sql, template_sha256=sha256(legacy_sql.encode()).hexdigest(),
                   evidence={'account_count': 4500})
        for version in ('financial-aggregates-v1', 'financial-aggregates-v2'):
            self.assertTrue(answer_has_disclosures(dict(old, catalog_version=version)))
            self.assertFalse(answer_has_disclosures(dict(new, catalog_version=version)))
        self.assertFalse(answer_has_disclosures(old))
        for changes in ({'positive_balance_sum': 0}, {'negative_balance_sum': 265470},
                        {'positive_account_count': 4459}, {'zero_balance_sum': 1}):
            self.assertFalse(answer_has_disclosures(dict(new, evidence=dict(new['evidence'], **changes))))

    def test_empty_templates_have_no_fabricated_utility_or_minutes(self):
        result = self.grade([])
        self.assertEqual(result['status'], 'awaiting_records')
        self.assertIsNone(result['mean_active_review_minutes'])
        self.assertEqual(result['answerable_cohort_size'], 0)
        self.assertIsNone(result['material_wrong_release_rate_per_eligible_request'])
        self.assertIsNone(result['material_wrong_release_rate_among_releases'])

    def test_answerable_holds_stay_in_utility_and_time_denominators(self):
        result = self.grade(self.rows(27, 3))
        self.assertEqual(result['status'], 'planning_thresholds_met')
        self.assertEqual(result['observed_original_correct_and_disclosed'], 27)
        self.assertEqual(result['answerable_holds_or_deferrals'], 3)
        rows = self.rows(26, 4)
        rows[-1].update(value_and_scope_correct='true', required_disclosures_present='true')
        result = self.grade(rows)
        self.assertEqual(result['status'], 'planning_thresholds_missed')
        self.assertEqual(result['observed_original_correct_and_disclosed'], 26)

    def test_missing_original_disclosure_cannot_be_replaced_by_a_reviewer_checkbox(self):
        rows = self.rows(27, 3)
        file = self.root / 'missing-caveat.json'
        original = json.loads((self.originals / (rows[0]['candidate_sha256'] + '.json')).read_text())
        original.pop('caveat')
        file.write_text(json.dumps(original))
        digest = capture(file, self.originals)
        rows[0].update(candidate_sha256=digest, reviewed_candidate_sha256=digest)
        result = self.grade(rows)
        self.assertEqual(result['status'], 'planning_thresholds_missed')
        self.assertEqual(result['observed_original_correct_and_disclosed'], 26)

    def test_missing_last_hold_is_detected_by_independent_intake(self):
        source = self.rows(30, 1)
        result = self.grade(source[:-1], source)
        self.assertEqual(result['status'], 'incomplete')
        self.assertEqual(result['intake_requests'], 31)

    def test_review_is_bound_to_preserved_original_bytes(self):
        rows = self.rows()
        rows[0]['reviewed_candidate_sha256'] = self.archive('hold')
        self.assertEqual(self.grade(rows)['status'], 'incomplete')
        candidate_path = self.originals / (rows[1]['candidate_sha256'] + '.json')
        candidate_path.write_text('{"action":"hold"}')
        self.assertEqual(self.grade(rows)['status'], 'incomplete')

    def test_missing_review_minutes_remains_unscored_and_601s_misses_threshold(self):
        rows = self.rows(seconds=601)
        self.assertEqual(self.grade(rows)['status'], 'planning_thresholds_missed')
        rows[9]['active_review_seconds'] = ''
        result = self.grade(rows)
        self.assertEqual(result['status'], 'incomplete')
        self.assertIsNone(result['mean_active_review_minutes'])
        rows[9].update(active_review_seconds='601', reviewer_ref='')
        self.assertIsNone(self.grade(rows)['mean_active_review_minutes'])
        self.assertIsNone(self.grade(self.rows(29))['mean_active_review_minutes'])

    def test_incident_on_nonanswerable_case_stops_full_queue(self):
        for incident in ('prohibited_effect', 'material_wrong_release'):
            with self.subTest(incident=incident):
                rows = self.rows(30, 1)
                rows[30].update(answerable='false', active_review_seconds='', reviewer_ref='')
                rows[30][incident] = 'true'
                result = self.grade(rows)
                self.assertEqual(result['status'], 'stop_for_incident')
                self.assertEqual(result['incident_request_ids'], ['test-only-31'])

    def test_all_released_components_in_the_window_require_both_review_judgments(self):
        for action, field, position in [('answer', 'value_and_scope_correct', 30),
                                        ('partial', 'required_disclosures_present', 30),
                                        ('partial', 'value_and_scope_correct', 1)]:
            with self.subTest(action=action, field=field, position=position):
                rows = self.rows(31)
                digest = self.archive(action)
                rows[position].update(candidate_sha256=digest, reviewed_candidate_sha256=digest)
                rows[position][field] = ''
                result = self.grade(rows)
                self.assertEqual(result['status'], 'incomplete')
                self.assertEqual(result['answerable_cohort_size'], 30)
                self.assertIsNone(result['material_wrong_release_rate_among_releases'])
                rows[position][field] = 'false'
                self.assertEqual(self.grade(rows)['status'], 'planning_thresholds_met')

    def test_release_risk_uses_both_denominators_and_keeps_incident_types_separate(self):
        rows = self.rows(3, 1)
        partial = self.archive('partial')
        rows[0].update(material_wrong_release='true', value_and_scope_correct='false')
        rows[1].update(candidate_sha256=partial, reviewed_candidate_sha256=partial,
                       eligible='false', answerable='false', material_wrong_release='true')
        rows[3]['prohibited_effect'] = 'true'
        result = self.grade(rows)
        self.assertEqual(result['status'], 'stop_for_incident')
        self.assertEqual(result['eligible_requests'], 3)
        self.assertEqual(result['would_be_releases'], 3)
        self.assertEqual(result['partial_answers'], 1)
        self.assertEqual(result['material_wrong_release_rate_per_eligible_request'], 1 / 3)
        self.assertEqual(result['material_wrong_release_rate_among_releases'], 2 / 3)
        self.assertEqual(result['material_wrong_release_request_ids'], ['test-only-1', 'test-only-2'])
        self.assertEqual(result['prohibited_effect_request_ids'], ['test-only-4'])
        rows[2]['material_wrong_release'] = ''
        self.assertIsNone(self.grade(rows)['material_wrong_release_rate_among_releases'])

    def test_original_scope_and_support_cannot_be_added_by_checkbox(self):
        rows = self.rows(27, 3)
        path = self.root / 'missing-scope.json'
        original = json.loads((self.originals / (rows[0]['candidate_sha256'] + '.json')).read_text())
        for field, value in [('evidence', {'other_count': 0}), ('parameters', {}), ('snapshot_sha256', 'unknown'),
                             ('unit', 'USD'), ('catalog_version', 'unknown'), ('role', 'unknown'),
                             ('template_sha256', 'unverified'), ('value', False)]:
            with self.subTest(field=field):
                path.write_text(json.dumps(dict(original, **{field: value})))
                digest = capture(path, self.originals)
                rows[0].update(candidate_sha256=digest, reviewed_candidate_sha256=digest)
                result = self.grade(rows)
                self.assertEqual(result['observed_original_correct_and_disclosed'], 26)
                self.assertEqual(result['status'], 'planning_thresholds_missed')

        cases = (
            ('mean_amount_by_duration', 'duration_months', 60,
             [{'months': 24}, {'months': True}, {'months': 60.0}], 6, {'months': 6}),
            ('approved_amount_by_year', 'origination_year', 1997,
             [{'start': '1996-01-01', 'stop': '1997-01-01'}], 2025,
             {'start': '2025-01-01', 'stop': '2026-01-01'}),
            ('vintage_finished_unpaid_share', 'vintage', 1997,
             [{'start': '1994-01-01', 'stop': '1995-01-01'}], 1996,
             {'start': '1996-01-01', 'stop': '1997-01-01'}),
        )
        with open_shadow() as session:
            for metric, field, scope, bad_params, unsupported, unsupported_params in cases:
                with self.subTest(metric=metric):
                    request = {'metric': metric, 'as_of': AS_OF, 'snapshot_sha256': SNAPSHOT_SHA, field: scope}
                    reply = evaluate(session, request)
                    self.assertTrue(answer_has_disclosures(reply))
                    for params in bad_params:
                        self.assertFalse(answer_has_disclosures(dict(reply, parameters=params)))
                    for bad_scope in (True, unsupported):
                        evidence = dict(reply['evidence'], **{field: bad_scope})
                        self.assertFalse(answer_has_disclosures(dict(reply, evidence=evidence,
                                                                   parameters=unsupported_params)))


if __name__ == '__main__':
    unittest.main()
