"""Portfolio loan aggregates, reconciled from individual contracts."""
from datetime import date

APPROVAL_DATE_NOTE = ('We use the recorded approval date (loan.date) as the origination date. '
                      'The snapshot has no separate disbursement date.')
DURATIONS = (12, 24, 36, 48, 60)
IDS = {'loan_status_counts', 'loan_duration_counts', 'approved_amount_by_year', 'mean_amount_by_duration'}


def catalog(Metric, currency):
    return {
        'loan_status_counts': Metric(
            'loans', 'Number of loans in each repayment status on the snapshot date.',
            'A and B are finished. C and D are running. Each loan contributes once.',
            """SELECT COUNT(CASE WHEN status='A' THEN 1 END), COUNT(CASE WHEN status='B' THEN 1 END),
                      COUNT(CASE WHEN status='C' THEN 1 END), COUNT(CASE WHEN status='D' THEN 1 END),
                      COUNT(*) FROM loan""", frozenset({('loan', 'status')})),
        'loan_duration_counts': Metric(
            'loans', 'Number of loans in each contractual duration in months.',
            'Each loan contributes once. The term is its original contractual duration.',
            """SELECT COUNT(CASE WHEN duration=12 THEN 1 END), COUNT(CASE WHEN duration=24 THEN 1 END),
                      COUNT(CASE WHEN duration=36 THEN 1 END), COUNT(CASE WHEN duration=48 THEN 1 END),
                      COUNT(CASE WHEN duration=60 THEN 1 END), COUNT(*) FROM loan""",
            frozenset({('loan', 'duration')})),
        'approved_amount_by_year': Metric(
            'source_units', 'Total approved amount for loans originating in the selected year.',
            APPROVAL_DATE_NOTE + ' ' + currency, """SELECT COUNT(*), COALESCE(SUM(amount), 0) FROM loan
                         WHERE date >= :start AND date < :stop""",
            frozenset({('loan', 'date'), ('loan', 'amount')})),
        'mean_amount_by_duration': Metric(
            'source_units', 'Arithmetic mean of approved amounts for loans with the selected contractual term.',
            'Each loan carries equal weight. ' + currency,
            'SELECT COUNT(*), SUM(amount) FROM loan WHERE duration = :months',
            frozenset({('loan', 'duration'), ('loan', 'amount')})),
    }


def base_counts(con, metric_id, scope):
    if metric_id == 'loan_duration_counts':
        counts = dict.fromkeys(DURATIONS, 0)
        for (months,) in con.execute('SELECT duration FROM loan'):
            counts[months] += 1
        return (*counts.values(), sum(counts.values()))
    if metric_id == 'loan_status_counts':
        counts = dict.fromkeys('ABCD', 0)
        for (status,) in con.execute('SELECT status FROM loan'):
            counts[status] += 1
        return (*counts.values(), sum(counts.values()))
    if metric_id == 'approved_amount_by_year':
        amounts = [amount for day, amount in con.execute('SELECT date, amount FROM loan')
                   if date.fromisoformat(day).year == scope]
    else:
        amounts = [amount for months, amount in con.execute('SELECT duration, amount FROM loan')
                   if months == scope]
    return len(amounts), sum(amounts)


def render(metric_id, counts, scope):
    if metric_id == 'loan_duration_counts':
        return {str(months): n for months, n in zip(DURATIONS, counts)}, {
            'loan_count': counts[-1], 'duration_unit': 'months'}
    if metric_id == 'loan_status_counts':
        return dict(zip('ABCD', counts[:4])), {'loan_count': counts[4]}
    count, total = counts
    if metric_id == 'approved_amount_by_year':
        return total, {'loan_count': count, 'origination_year': scope}
    if count == 0:
        raise ValueError('There are no loans of this duration.')
    return total / count, {'loan_count': count, 'approved_amount_sum': total, 'duration_months': scope}
