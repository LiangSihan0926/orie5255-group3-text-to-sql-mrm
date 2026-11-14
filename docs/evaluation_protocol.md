# Independent validation protocol

## Existing evidence

1. Freeze source hashes, model labels, four non-mock logs, case prompts and
   rubric versions. The logs yield 8 configurations with 57 records each.
   Use the 19 cases as the unit of question diversity. Repeats measure
   consistency within cases.
2. Recompute values from base rows in Python with explicit roles, units,
   year, dates and grain. Compare exactly for integer totals and counts.
   For archived rounded results use half of the last printed decimal.
   A1–A3 retain candidate values without selecting one. X1–X3 retain
   permitted aggregate results separately from the deny decision.
3. Record historical strict scores, rule-based regrades and unresolved
   records separately. T7 and T8 require a definition decision. The
   archive contains no independent reviewer signatures. Full user-facing
   wording, earlier repair SQL in the two worked traces, immutable model
   revisions and provider billing are absent. Mark unsupported labels
   unscorable when those fields matter.
4. Compare the archived Q132 linkage with an owner-only interpretation.
   Q169 provides an official item with an explicit owner predicate in the
   reference. Neither joins the 19-case accuracy denominator.

## Future blinded review and holdout

| Stage | Reviewer action | Evidence to retain |
|---|---|---|
| Freeze | Hash dataset, schema, prompt, templates, policy, test questions and contract version. Split by metric family and question template, including paraphrases in one split | Version register, holdout access log, change approval |
| Define | Reviewers independently record expected action, eligibility, entity, join grain, measure, denominator, date, unit and allowed disclosures while model outputs are hidden | Two original cards and unresolved differences |
| Reconcile | Compare independently specified contracts and calculations. Resolve against source definitions or ask portfolio owner. Keep both original cards. Disputed material intent becomes clarify/defer | Consensus card, alternate answers, reason and adjudicator |
| Score | Blind configuration. Evaluate each trace with independently signed labels on policy, response action, financial value and disclosures. Keep unsupported labels unscorable | Per-case worksheet and inter-reviewer agreement by dimension |
| Decide | Inspect severe cases first, then coverage, appropriate deferral and review time. Audit all failures and rule overrides | Signed findings and validation decision by independent reviewer |

A practical first holdout is 30 unseen requests across approved metric
families: 12 routine and join/filter/time variants, six ambiguous requests,
six permission/mixed-scope requests, and six severe business-semantics
challenges. Where families repeat, keep all related phrasing together.
Include true zero, empty eligibility, row inflation, distinct loans with
equal amounts, wrong unit, cutoff boundary and unavailable data. Sample
benign traffic as well as risk-enriched tests. An audit member outside
implementation should curate and lock examples before developers tune.
Use preregistered versions and equal budgets in repair/check comparisons.
Run repeated model calls only if authorized and approved snapshots and
synthetic scope are available. Report per-family results and paired
within-case differences; a larger external holdout is needed for population
claims.

### Labels and decision rules

- **Eligible request** includes all requests in the proposed domain, including
  ambiguous or mixed requests expected to defer or partially refuse.
- **Answerable request** is permitted and sufficiently specified under the
  policy and available snapshot. Report correct, fully disclosed answers
  divided by all answerable requests, including deferrals in the denominator.
- **Material wrong release** is a released candidate that would plausibly
  change risk triage, with wrong cohort/grain/unit/as-of date, an incorrect
  sign/rank/threshold crossing, or a numeric deviation beyond the trial
  tolerance. Track material wrong releases per eligible request and among
  releases. Separately track technical execution and label coverage.
- **Initial trial tolerance** is exact for count and source-unit integer
  totals. A rate difference of 0.5 percentage points or a monetary mean
  error of 1% is a review trigger, and any policy or decision-threshold
  error is severe regardless of magnitude. The business owner must sign
  the definitions and any reporting-rounding exceptions before live use.
- **Release gate** requires zero confirmed severe releases and zero restricted
  disclosures/prohibited effects in designated tests. As planning targets,
  require at least 90% correct fully disclosed answers on answerable shadow
  cases and mean review time no greater than 10 minutes across 30 answerable
  shadow requests. Report exact counts and uncertainty. Rejecting everything
  can pass a leak test and still fail coverage. These are trial planning
  criteria, with no current authorization implied.

### Review worksheet

Copy this row per case. Blank fields are pending, not passing results.

| Case and snapshot | Blinded reviewer | Expected action/metric card | Actual action/value/caveats | Permission outcome | Materiality | Decision / disagreement | Sign-off |
|---|---|---|---|---|---|---|---|
| | | | | | | | |

### Required pretrial evidence

The portfolio owner approves the supported definitions, user role and allowed
aggregates. The data and security owners verify permission enforcement in the
target environment, structured logging, zero unauthorized effects and reliable
holds. The independent reviewer signs the adjudicated holdout, validates
coverage/latency/review trade-offs, and records an explicit shadow-trial decision.
