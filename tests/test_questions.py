from copy import deepcopy
import unittest

from validation.question_replay import check_response
from validation.questions import answer_question
from validation.shadow import open_shadow


class EnglishQuestionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        connection = open_shadow()
        cls.session = connection.__enter__()
        cls.addClassCleanup(connection.__exit__, None, None, None)

    def test_ordinary_numeric_forms(self):
        pairs = (
            ('How many loans are there in each repayment status?', {'A': 203, 'B': 31, 'C': 403, 'D': 45}),
            ('What is the TOTAL approved loan amount for loans approved in 1997?', 30731364),
            ('What is the average approved amount of 60-month loans?', 35445360 / 145),
        )
        for question, value in pairs:
            with self.subTest(question=question):
                answer = answer_question(self.session, question)
                self.assertEqual(answer['action'], 'answer')
                self.assertEqual(answer['value'], value)

    def test_year_term_and_unrecognized_modifier(self):
        for question in ('What is the total approved loan amount for loans approved in 2025?',
                         'What is the average approved amount of 6-month loans?',
                         'What is the average approved amount of 60-month loans in Prague?'):
            with self.subTest(question=question):
                self.assertEqual(answer_question(self.session, question)['action'], 'hold')

    def test_cutoff_and_proxy_resolution(self):
        first = answer_question(self.session, 'How many loans were active (running) at the end of 1996?')
        self.assertEqual(first['action'], 'clarify')
        second = answer_question(self.session, 'How many loans were scheduled to be active on 1996-12-31?')
        self.assertEqual(second['value'], 247)
        vintage = answer_question(self.session, 'For 1997 originations, what share of finished loans had status B at the snapshot?')
        self.assertEqual(vintage['evidence']['denominator'], 43)
        self.assertEqual(vintage['value'], 3 / 43)

    def test_currency_and_role_apply_before_disclosure(self):
        q = 'What is the total approved loan amount in US dollars?'
        answer = answer_question(self.session, q)
        self.assertEqual(answer['action'], 'partial')
        self.assertEqual(answer['withheld_unit'], 'USD')
        self.assertEqual(answer['permitted_answer']['value'], 103261740)
        self.assertEqual(answer['permitted_answer']['unit'], 'source_units')
        denied = answer_question(self.session, q, role='guest')
        self.assertEqual(denied['action'], 'hold')
        self.assertNotIn('permitted_answer', denied)

    def test_replay_rejects_same_amount_with_wrong_scope_or_missing_disclosures(self):
        reply = answer_question(self.session, 'What is the total approved loan amount for loans approved in 1997?')
        refs = {'numeric_reference': {'E2': [(30731364,)]},
                'english_replay_support': {'E2': {'origination_year': 1997, 'loan_count': 196}}}
        self.assertTrue(check_response('E2', reply, refs)[1])
        for field, value in [('metric', 'approved_loan_total'), ('as_of', '1997-12-31'),
                             ('evidence', {'origination_year': 1997, 'loan_count': 1}),
                             ('parameters', {}), ('definition', ''), ('caveat', ''), ('sql', '')]:
            with self.subTest(field=field):
                self.assertFalse(check_response('E2', dict(reply, **{field: value}), refs)[1])

    def test_replay_checks_specific_clarification_and_withheld_component(self):
        missing_status = {'action': 'clarify', 'question': 'Which weight and region?'}
        self.assertFalse(check_response('A1', missing_status, {})[1])
        original_a2 = answer_question(self.session, 'How many customers have loans?')
        self.assertTrue(check_response('A2', original_a2, {})[1])
        self.assertFalse(check_response('A2', {'action': 'clarify',
                                    'question': 'Account owner or any client linked to a borrowing account?'}, {})[1])
        proper = answer_question(self.session, 'Which region has the highest default rate?')
        self.assertTrue(check_response('A1', proper, {})[1])
        self.assertFalse(check_response('A1', dict(proper, permitted_answer={'value': 0}), {})[1])
        reply = answer_question(self.session, 'What is the total approved loan amount in USD?')
        refs = {'numeric_reference': {'T10': [(103261740,)]},
                'english_replay_support': {'T10': {'loan_count': 682}}}
        self.assertTrue(check_response('T10', reply, refs)[1])
        wrong = deepcopy(reply)
        wrong['permitted_answer']['unit'] = 'USD'
        self.assertFalse(check_response('T10', wrong, refs)[1])
        self.assertFalse(check_response('T10', dict(reply, value=1), refs)[1])
