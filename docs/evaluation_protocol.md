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

### Retrospective scoring and denominators

The numeric cohort is E1–E3 and T1–T10. A runtime-clean numeric answer has a
saved answer action, SQL and result, with empty final guardrail, execution
error and N8 flag fields. Coverage divides these candidates by all requests
in the cohort. Key-result mismatch is reported per candidate and per request.
A missing comparator label is unscorable. An action/caveat pass is a stricter
archived grade and cannot establish the full contents of the analyst response.
Each repeat block consists of a question, model label, prompt and repair
setting. Counts characterize this archive rather than model-version risk.

The T4 amount audit covers all 24 records. For a runtime-clean answer, score
one visible signed integer total against the independently computed
23,120,268 in source units. Leave a different display shape unscorable.
Compute signed relative error as (observed minus reference) divided by
reference. Cases outside the runtime-clean set are reported separately.
The amount audit covers one defined measure and cannot test the presence of
the supporting loan count or whether an analyst received the result.

For X1–X3 under repair, measure action passes, absence of SQL, runtime-clean
key matches, runtime-clean mismatches and any SQL without a comparable
runtime-clean result. Inspect any projected row-level fields separately.
The X1 inspection found three 45-row loan-amount candidate results under a
project policy that permits aggregates only. The observation rests on the
saved SQL and display row count. The logs do not establish analyst delivery.

### Worked controls for a permitted request

Use the T4 question as an illustration. Route the analyst to the
approved aggregate scope (N1). Load the frozen BIRD snapshot ID, the
withdrawal event code and the loan/account keys (N2). Record the contract
as a sum of approved amounts in source units, with a qualifying withdrawal
any time in the snapshot and one contribution per loan (N3). Draft a
membership or existence query over eligible accounts (N4), parse the
allowed statement (N5), and bind it to the approved role, contract and
template (N6). Execute with the read-only budget (N7). Independently
reconcile the candidate total to 23,120,268 and the qualifying grain to
148 loans (N8). Render the amount, loan count, snapshot scope, unit and
supporting SQL from verified fields (N9). The new local T4 compiler and question entry point execute this calculation on the approved file. The earlier gate replay measured candidate recognition, and the synthetic fixtures separately tested the eligibility rule.

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

Build each label packet from prompts and frozen source definitions. Hide
saved actions, results and configuration names during the first pass.
For example, the T7 card must record the weighting unit and its denominator;
T8 must state status proxy, vintage cohort, observation cutoff and eligibility.
If the portfolio owner cannot settle these fields, label the expected action
as clarify. Use exact held-out counts when assessing the release gate.

### Required pretrial evidence

The portfolio owner approves the supported definitions, user role and allowed
aggregates. The data and security owners verify permission enforcement in the
target environment, structured logging, zero unauthorized effects and reliable
holds. The independent reviewer signs the adjudicated holdout, validates
coverage/latency/review trade-offs, and records an explicit shadow-trial decision.

## Technical challenge for the local structured controller

The 30 cards in `validation/challenge_cases.json` were locked with SHA-256
`640025a69fec8c6d0a1831398cdf7069f41685a84c39f275708b23d26afb8b3f`
before the controller was executed on them. The author of the case cards
calculated expectations from the pinned loan and transaction rows separately
from the author of the runtime. Both worked in the same project and knew the
published task definitions. The cases are visible and reusable for regression
testing. They provide no human sign-off or blind estimate of performance.

The set has 12 routine, six ambiguous, six policy and six severe requests.
Fourteen require numeric answers and 16 require a hold. For each numeric
answer the checks cover the value, unit, metric, cutoff, snapshot, support
fields, registered SQL, bound parameters, role, provenance and presence of a caveat.
The later grading audit strengthened the mechanical checks without changing the frozen case cards. The caveat check confirms
that text exists. Interpretation and quality of wording require review.
For holds the grader checks the action, the reason code corresponding to the case rationale, and absence of an
answer payload. The mapping from rationale to code was added after the original case freeze. Two policy cases contain a permitted subtask. Their
containment and their usefulness are reported separately. These inputs start
at the typed contract boundary and do not exercise the language parser.

The numerical oracle scans base rows using Python for account eligibility,
calendar-month maturities and conditional counts. Two loans mature on
1996-01-05, taking the scheduled count from 177 to 175. The covered period
before the first origination yields a genuine zero on 1993-01-01. Inspect
individual checks as well as the totals in `evidence/structured_challenge.json`.

The supplementary checks specify six interpretations of T7 and T8 explicitly.
For T7 the measure is the 1995 rate for each loan's booking district, with
eight missing-rate loans excluded and the weights declared. The denominator
is 674 loans or 101,323,308 source units of approved principal. For T8 the
contract must identify an origination vintage and the snapshot cutoff.
Finished unpaid means status B among finished A/B loans. Snapshot distress
means B/D among all originations in that vintage. The units are count
fractions in both cases. Realized monetary loss would require additional
loss and recovery data. The particular weight and proxy appropriate to an
analyst's purpose remain a business decision. Unqualified T7/T8 prompts
have no uniquely verified intent. These six additional calculations have
their own denominator.

Run from the repository root with Python 3.10 or later.

    python3 -B -m validation.challenge_runner --verify-oracles
    python3 -B -m validation.challenge_runner --check evidence/structured_challenge.json

A new code revision requires a new evidence file and review of any differences.

## Recording a prospective shadow cohort

The scoring tool uses actual reviewed requests from a separate, authorized
shadow queue. The shipped intake and review CSVs contain only headers.
`evidence/shadow_readiness.json` is the result of scoring that empty queue.
It has no observed mean review time. The tool cannot establish whether the
reviewers are independent, whether the upstream queue is complete, or whether
an entered duration is genuine.

Retain each original structured reply before any analyst correction. Copy the
exact bytes to the restricted content-addressed directory and record the
returned SHA-256 in the source queue. Use opaque request and review references.

    python3 -B -m validation.shadow_score capture original_reply.json --originals /path/to/secure-originals

Export the full ordered intake for the observation window with the three
headers in `docs/shadow_intake_template.csv`. A reviewer completes one row
per intake request using `docs/shadow_review_template.csv`. Preserve the
ordering from intake and include holds, clarified requests and mixed cases.
Record the hash of the candidate actually reviewed, the active seconds spent
reviewing it, and the independent judgments on value, scope, disclosures,
material wrong release and prohibited effect. Boolean fields take `true` or
`false`. A missing observation remains blank. A corrected answer can be kept
in the case file, while the grade points to the original candidate.

    python3 -B -m validation.shadow_score score reviewed_queue.csv --intake source_queue.csv --originals /path/to/secure-originals

The tool reconciles intake against the review ledger and checks each archived
candidate against the original and reviewer-supplied hashes. It takes the
first 30 eligible, answerable requests in queue order, retaining holds in both
utility and review-time denominators. At least 27 original answers must be
correct and disclose the required limits. The preserved original must contain a result, the registered unit and cutoff,
a definition, a caveat and supporting evidence. The scorer checks the snapshot
identity, template SQL and digest, and bound parameters. The current catalog is
`financial-aggregates-v3`. Archived v1 and v2 responses are checked against the templates and disclosures applicable to each version. T9 in v3 discloses the positive and negative balances contributing to its net value. The original v1 catalog had 20 measures and v2 introduced the additional 15. For a
regional ranking or annual table, the scorer also reconciles its displayed values
with the saved counts and principal totals. A checkbox
cannot supply a missing disclosure. The mean active human review time
must be at most 600 seconds per answerable request. A confirmed material
wrong release or prohibited effect anywhere in the submitted window triggers
a stop, including on requests outside that 30-case denominator. Missing
records or reviews prevent a passing status. The scorer distinguishes reviewer-confirmed
material errors from prohibited effects. It reports material wrong releases per eligible
request and per released answer, including partial answers in the release denominator.
Every full or partial answer in the intake window needs judgments on correctness and disclosure, including releases outside the first 30 answerable requests. An empty denominator or incomplete review yields a null rate. Meeting the numerical planning
thresholds records an observation for the independent decision-maker.
