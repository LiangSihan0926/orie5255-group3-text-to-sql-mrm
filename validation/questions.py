"""Run one supported analyst question against the frozen financial snapshot."""
import argparse
from hashlib import sha256
import json
import re
import sqlite3

from . import owner_year, regional
from .reference import AS_OF, SNAPSHOT_SHA
from .shadow import ROLE, evaluate, hold, open_shadow

# Each full sentence authorizes one meaning. Modifiers left over from a match
# can change the population, time or unit, so substring matches are unsuitable.
QUESTION_FORMS = {
    'delinquent_owner_age_bands': ('Show status D loan counts and total approved principal by owner age band at the 1998 snapshot',),
    'loan_duration_counts': ('Show the number of loans by duration',),
    'loan_status_counts': ('How many loans are there in each repayment status',),
    'moravia_booking_distressed_share': ('What is the bad-loan rate (by count) for loans booked in the two Moravian regions combined',),
    'female_owner_mean_approved_amount': ('What is the average approved loan amount for loans whose borrower is female',),
    'prague_owner_distressed_share': ('What is the bad-loan rate (by count) for borrowers who live in Prague',),
    'closing_deposit_balance': ('What was the total deposit balance across all accounts at 1998-12-31',),
    'withdrawal_loan_amount': (
        'What is the total approved loan amount of accounts that have made at least one card withdrawal',
        'How much was approved in loans on accounts with at least one card withdrawal',
        'Sum the approved loan amounts for accounts with a card withdrawal',
    ),
    'approved_loan_total': (
        'What is the total approved loan amount in source units',
        'What is the total approved loan amount across the portfolio',
    ),
    'distressed_loan_share': (
        'What share of loans have status B or D',
        'What is the portfolio bad-loan rate by loan count',
    ),
    'distressed_approved_amount_share': (
        'What is the bad-loan rate of the portfolio, weighted by approved amount',
        'What share of approved loan amount belongs to loans with status B or D',
    ),
    'finished_unpaid_share': (
        'What share of finished loans have status B',
    ),
    'district_unemployment_1995_by_loan_count': (
        'What was the average 1995 booking-district unemployment rate with equal weight per loan',
    ),
    'district_unemployment_1995_by_approved_amount': (
        'What was the average 1995 booking-district unemployment rate weighted by approved loan amount',
    ),
    'running_delinquent_share': (
        'What share of running loans have status D',
    ),
}
QUESTION_FORMS.update(regional.QUESTION_FORMS)
QUESTION_FORMS[owner_year.OWNERS] = (
    'How many distinct owners of accounts with an originated loan appear in the 1998-12-31 snapshot',
    'How many distinct owners of loan accounts are there in the snapshot',
)
QUESTION_FORMS[owner_year.YEAR_PROFILE] = (
    'Show the average approved loan amount by origination year in source units',
    'What was the average approved loan amount in each origination year',
    'Show the average approved loan amount by origination year',
)
CLARIFICATIONS = {
    'Which region has the highest default rate':
        'Which status definition, weight (loan count or approved amount), and region (booking branch or owner residence) should determine the ranking?',
    'How many customers have loans':
        'Do you mean each distinct account owner, any client linked to a borrowing account, or the accounts '
        'themselves? This interface counts distinct owners. A count of all linked clients or borrowing '
        'accounts as the requested measure needs a separate review.',
    'What was the average loan size last year':
        'Which calendar year should we use for loan origination? The recorded date is the approval date.',
    'What is the loan-weighted average 1995 unemployment rate of the districts where loans are booked':
        'Should each loan count once, or should its approved amount determine its weight? Should loans with missing district rates be excluded and counted separately?',
    'Compare the loss rate of loans originated in 1994 versus 1997':
        'Do you need realized monetary loss, the unpaid share of finished loans, or the B/D distress share of all originations? The snapshot does not record realized monetary loss.',
}
FX_QUESTIONS = (
    'What is the total approved loan amount in US dollars',
    'What is the total approved loan amount in USD',
)
BOTH_UNITS = 'What is the total approved loan amount in source units and US dollars'
FX_REASON = 'The catalog has no approved exchange rate and conversion date. The permitted amount is disclosed in source units.'


# Only these archived byte-for-byte requests have audited splits. The digest selects
# an existing aggregate contract; the request text is never passed to SQLite.
MIXED_REQUESTS = {
    # X1 permits a three-band portfolio summary and denies individual dates and amounts.
    'd50b6c1926b637ba0aeb0e11030f3b1c90835704e02ccbed940a1f2b82dbb3fd': (
        'delinquent_owner_age_bands', 'individual_birth_dates_and_loan_amounts',
        'Individual birth dates and loan amounts are refused. The summary shows loan counts '
        'and total approved principal for three owner age bands.'),
    # X2 permits a portfolio count rate and denies a request to change the loan ledger.
    '2a4f8742b9446d8aae898576b5de4edcb6d6dfe9d71799ffee0ee130ae63eec9': (
        'distressed_loan_share', 'modify_loan_records',
        'Only the B/D count share is provided. The requested record deletion is refused. '
        'The request to alter reported figures requires data-owner review.'),
    # X3 permits a distribution by term and denies an authority change and table removal.
    '62f17815208df33a0a28dc92014984f5a385bc120945f7f015dab83dcca02830': (
        'loan_duration_counts', 'change_role_or_remove_table',
        'Only counts by contract duration are provided. The requested role change and '
        'table removal are refused and require data-owner review.'),
}


def partial_answer(result, explanation, **withheld):
    if result['action'] != 'answer':
        return result
    return {'action': 'partial', 'permitted_answer': result, 'explanation': explanation, **withheld}


def normalize(question):
    return ' '.join(question.casefold().split()).rstrip('?.').rstrip()


METRICS = {normalize(form): metric for metric, forms in QUESTION_FORMS.items() for form in forms}
ASK = {normalize(question): detail for question, detail in CLARIFICATIONS.items()}


def answer_question(session, question, *, role=ROLE):
    if role != ROLE:
        return {'action': 'hold', 'reason': 'role_not_authorized'}
    if not isinstance(question, str) or not question.strip() or len(question) > 1000:
        return {'action': 'hold', 'reason': 'invalid_question'}
    digest = sha256(question.encode('utf-8', errors='surrogatepass')).hexdigest()
    if digest in MIXED_REQUESTS:
        metric, withheld_action, explanation = MIXED_REQUESTS[digest]
        permitted = evaluate(session, {'metric': metric, 'as_of': AS_OF, 'snapshot_sha256': SNAPSHOT_SHA}, role=role)
        return partial_answer(permitted, explanation, withheld_action=withheld_action, review_required=True)
    text = normalize(question)
    if text in ASK:
        return {'action': 'clarify', 'question': ASK[text]}
    if re.fullmatch(r'how many loans were active \(running\) at the end of \d{4}', text):
        return {'action': 'clarify', 'question': 'Do you mean active under the contract schedule or actually performing on that date? Only scheduled activity can be reconstructed.'}

    as_of = AS_OF
    schedule = re.fullmatch(r'how many loans were scheduled to be active (?:on|as of) (\d{4}-\d{2}-\d{2})', text)
    metric = METRICS.get(text)
    vintage = re.fullmatch(r'for (1994|1997) originations, what (share of finished loans had status b|share of all loans had status b or d) at the snapshot', text)
    year = re.fullmatch(r'what is the total approved loan amount for loans approved in (\d{4})', text)
    mean_year = re.fullmatch(
        r'what was the average approved loan amount in source units for loans originated in calendar year ([0-9]{4})'
        r'|what was the average approved loan amount for loans originated in ([0-9]{4})', text)
    term = re.fullmatch(r'what is the average approved amount of (\d{1,3})-month loans', text)
    partial = text in {normalize(q) for q in (*FX_QUESTIONS, BOTH_UNITS)}
    if schedule:
        metric, as_of = 'scheduled_active_loans', schedule.group(1)
    elif vintage:
        metric = ('vintage_finished_unpaid_share' if vintage.group(2) == 'share of finished loans had status b'
                  else 'vintage_distressed_loan_share')
    elif year:
        metric = 'approved_amount_by_year'
    elif mean_year:
        metric = owner_year.YEAR_MEAN
    elif term:
        metric = 'mean_amount_by_duration'
    elif partial:
        metric = 'approved_loan_total'
    elif metric is None:
        return {'action': 'hold', 'reason': 'outside_question_catalog',
                'explanation': 'The wording or requested scope falls outside the local catalog.'}

    contract = {'metric': metric, 'as_of': as_of, 'snapshot_sha256': SNAPSHOT_SHA}
    if vintage:
        contract['vintage'] = int(vintage.group(1))
    if year:
        contract['origination_year'] = int(year.group(1))
    if mean_year:
        contract['origination_year'] = int(mean_year.group(1) or mean_year.group(2))
    if term:
        contract['duration_months'] = int(term.group(1))
    result = evaluate(session, contract, role=role)
    if partial:
        return partial_answer(result, FX_REASON, withheld_unit='USD')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('question', nargs='?')
    parser.add_argument('--list', action='store_true', help='Print supported English question forms')
    args = parser.parse_args()
    if args.list:
        forms = [q + '?' for group in QUESTION_FORMS.values() for q in group]
        forms += ['What is the total approved loan amount for loans approved in YEAR?',
                  'What is the average approved amount of N-month loans?',
                  'What was the average approved loan amount in source units for loans originated in calendar year YEAR?',
                  *FX_QUESTIONS]
        forms += ['How many loans were scheduled to be active on YYYY-MM-DD?', BOTH_UNITS + '?']
        forms += ['For YEAR originations, what share of finished loans had status B at the snapshot?',
                  'For YEAR originations, what share of all loans had status B or D at the snapshot?']
        print('\n'.join(forms))
        print('Vintage questions accept 1994 and 1997.')
    elif args.question:
        try:
            with open_shadow() as session:
                result = answer_question(session, args.question)
        except (OSError, EOFError, ValueError, sqlite3.Error):
            result = hold('source_unavailable', 'The pinned snapshot could not be verified and opened.')
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        parser.error('supply a question or --list')


if __name__ == '__main__':
    main()
