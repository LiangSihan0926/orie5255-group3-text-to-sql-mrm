"""The frozen challenge must reject a matching number with wrong financial evidence."""
from copy import deepcopy
import unittest

from validation.challenge_runner import HOLD_REASON_BY_CARD, load_cards, score, summarize
from validation.shadow import evaluate, open_shadow


class ChallengeScoringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cards = {card['id']: card for card in load_cards()}

    def test_matching_rate_needs_the_declared_denominator_and_unit(self):
        card = self.cards['R03']
        with open_shadow() as session:
            response = evaluate(session, card['request'], role=card['role'])
        self.assertTrue(score(card, response)['passed'])
        wrong_population = deepcopy(response)
        wrong_population['evidence']['denominator'] -= 1
        self.assertFalse(score(card, wrong_population)['checks']['supporting_fields'])
        self.assertFalse(score(card, dict(response, unit='percent'))['checks']['unit'])

    def test_a_hold_must_not_carry_a_numeric_or_nested_answer(self):
        card = self.cards['P05']
        hold = {'action': 'hold', 'reason': 'unsupported_request', 'message': 'Restricted request.'}
        self.assertTrue(score(card, hold)['passed'])
        self.assertFalse(score(card, dict(hold, value=0))['checks']['no_answer_payload'])
        self.assertFalse(score(card, dict(hold, permitted_answer={'value': 0}))['checks']['no_answer_payload'])

    def test_timeout_does_not_verify_the_sixteen_distinct_hold_cards(self):
        timed_out = {'action': 'hold', 'reason': 'timeout', 'message': 'Took too long.'}
        rows = [score(self.cards[cid], timed_out) for cid in HOLD_REASON_BY_CARD]
        result = summarize(rows)
        self.assertEqual(result['holds_with_reason_and_no_answer_payload'], 16)
        self.assertEqual(result['holds_matching_the_recorded_rationale'], 0)
        self.assertEqual(result['complete_technical_checks_passed'], 0)

    def test_agreeing_value_with_wrong_template_cutoff_or_support_fails_receipt_review(self):
        card = next(c for c in self.cards.values() if c['request'].get('metric') == 'scheduled_active_loans'
                    and c['expected']['action'] == 'answer')
        with open_shadow() as session:
            answer = evaluate(session, card['request'], role=card['role'])
        for changes in ({'sql': 'different recorded template'}, {'parameters': {'as_of': '1998-12-30'}},
                        {'evidence': {'loan_count': answer['value'] + 1}}):
            with self.subTest(changes=changes):
                row = score(card, dict(answer, **changes))
                self.assertTrue(row['frozen_card_checks_passed'])
                self.assertFalse(row['passed'])

    def test_failed_partial_answer_stays_in_the_release_denominator(self):
        partial = {'action': 'partial', 'permitted_answer': {'value': 0}}
        row = score(self.cards['P05'], partial)
        summary = summarize([row])
        self.assertFalse(row['passed'])
        self.assertEqual(summary['would_be_answers'], 1)
        self.assertEqual(summary['would_be_partial_answers'], 1)
        self.assertEqual(summary['would_be_answers_failing_a_registered_check'], 1)


if __name__ == '__main__':
    unittest.main()
