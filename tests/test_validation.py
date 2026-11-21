import tempfile
import unittest
from collections import Counter
from pathlib import Path

from validation import controls, reference
from validation.run import run


class ValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = run()

    def test_archive_and_references_reconcile(self):
        self.assertEqual(self.report['pilot']['runs'], 456)
        self.assertEqual(self.report['pilot']['strict_verdicts']['PASS'], 192)
        comparisons = self.report['reference_comparison']
        self.assertEqual(len(comparisons), 19)
        self.assertTrue(all(row['recorded_match'] for row in comparisons))
        self.assertEqual(self.report['references']['numeric_reference']['T4'], [(23120268, 148)])

    def test_t4_gate_drops_mismatches_in_archive(self):
        rows = self.report['t4_archive_replay']
        baseline = [row for row in rows if row['base_release_proxy']]
        gated = [row for row in rows if row['gated_release_proxy']]
        self.assertEqual((len(baseline), len(gated)), (11, 6))
        self.assertTrue(all(row['matched_key_result'] for row in gated))
        different_contract = controls.Contract('account holds a card','loan','approved amount','source units',None)
        self.assertFalse(controls.accepted(controls.IN, different_contract))

    def test_runtime_proxy_and_strict_labels_have_separate_denominators(self):
        pilot = self.report['pilot']
        traps = pilot['numeric_by_family']['trap']
        self.assertEqual((traps['requests'], traps['runtime_clean'], traps['key_mismatch']), (240, 164, 81))
        self.assertEqual(pilot['trap_strict_repeat_blocks'], {'0': 57, '1': 0, '2': 1, '3': 22})
        self.assertEqual(pilot['numeric_candidates']['rule_labeled_review_within_clean_mismatches'], {'T7': 12})
        self.assertEqual(Counter(r['outcome'] for r in self.report['t4_amount_audit']), {
            'exact total': 12, 'wrong total': 8, 'outside runtime-clean answer set': 4,
        })

    def test_reference_sensitivity_changes_weight_or_denominator_explicitly(self):
        evidence = self.report['references']['illustrations']
        t7 = evidence['T7_weight_sensitivity']
        self.assertEqual(t7['included_loans'] + t7['excluded_loans'], 682)
        self.assertAlmostEqual(t7['count_weighted_percent'], 2.8421365)
        self.assertAlmostEqual(t7['amount_weighted_percent'], 2.7719750)
        first, later = evidence['T8_vintage_sensitivity']
        self.assertEqual((first['finished_loans'], later['finished_loans']), (85, 43))
        self.assertEqual((first['finished_status_b'], later['finished_status_b']), (12, 3))

    def test_fixture_gate_and_mutations_have_different_errors(self):
        rows = self.report['t4_fixtures']['candidates']
        self.assertTrue(all(row['semantically_correct'] == row['passes_all'] for row in rows))
        self.assertEqual(sum(row['semantically_correct'] and not row['gate_accepts'] for row in rows), 2)
        self.assertEqual(sum(not row['semantically_correct'] and row['passes_base'] for row in rows), 3)
        self.assertEqual(sum(not row['semantically_correct'] and row['passes_two_proposed_variants'] for row in rows), 1)

    def test_snapshot_identity_checked_before_use(self):
        with tempfile.TemporaryDirectory() as directory:
            wrong = Path(directory) / 'other.sqlite'
            wrong.write_bytes(b'not the pilot snapshot')
            with self.assertRaisesRegex(ValueError, 'does not match'):
                with reference.snapshot(None, db=wrong):
                    self.fail('unexpected connection')


if __name__ == '__main__':
    unittest.main()
