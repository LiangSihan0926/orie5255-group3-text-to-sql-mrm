# Node-level validation and monitoring

The nine functions below describe the proposed production boundary. In the
archived pilot N1–N4 shared a single model call. N5/N6 used lightweight
statement and projection checks, N7 used SQLite read-only and fetched at most
1,000 rows, and N8 used a generic check only with repair enabled. N9 evidence
consists of the final structured action, SQL, assumptions and result excerpt.
The revised local controller implements fixed metric templates, column permissions, base-row reconciliation and deterministic rendering. A bank service still needs authenticated roles and independent access tests.

## A. Failure propagation

High (H) means a credible restricted disclosure, prohibited action, or
decision-changing portfolio misstatement. Medium (M) means an analyst can
recover with material rework or degraded service. Severity rises when a
failure leads to a high-impact release.

| Node and boundary | Failure and cause | Propagation | Business impact |
|---|---|---|---|
| N1 Route request | Defaults ambiguous borrower or date; prompt treated as authority | N3 resolves wrong contract; N4 generates plausible query | H misdirected investigation; M clarification delay |
| N2 Supply approved context | Stale schema/value map; copied metadata calls amounts USD | N3 or N4 uses wrong definition, field or code | H materially wrong units; M repeated execution failure |
| N3 Resolve metric | Substitutes card ownership for withdrawal or chooses amount instead of loan count | Wrong cohort, measure or grain persists through all checks | H skewed aggregate, concentration ranking or false trend |
| N4 Draft or repair | Join multiplies loans; rewrite addresses execution while changing population | N5 and N7 may accept SQL and N8 sees a plausible number | H portfolio overstatement; M retry cost and vendor dependence |
| N5 Check syntax and action | Action/statement disagree; parser incompatible with SQLite dialect | Ineligible statement reaches authorization gate or valid answer is held | H prohibited action if other controls also fail; M work backlog |
| N6 Enforce permission and intent | Read-only mistaken for confidentiality; weak projection screening; broken grain | Excess data or wrong cohort reaches N7 and possibly output or logs | H privacy/infosec exposure or misleading aggregate; possible compliance and reputational harm |
| N7 Execute approved query | Deadline, stale snapshot, incomplete results or non-atomic snapshot | Partial or stale numbers accepted downstream | H wrong date basis if released; M availability and investigation delay |
| N8 Validate result | Non-zero wrong aggregate passes; valid zero erroneously flagged | Wrong candidate released or correct answer repeatedly withheld | H inaccurate risk triage; M avoidable retries and review |
| N9 Release or defer | Rephrasing changes units, drops caveat, sends narrow outputs to unauthorized recipient | Analyst treats proxy as realized loss or a tentative amount as final | H decision, privacy, and audit impact; M avoidable rework |

## B. Evaluation, controls and residual risks

| Node | Offline test, metric and reference | Proposed online guardrail | Residual risk |
|---|---|---|---|
| N1 | A1–A3 and benign paraphrases. Correct action and completeness of discriminating question against intent card | On unresolved material field, ask a specific clarification and stop; reject untrusted requests for prohibited actions | Ambiguity implicit in local business language |
| N2 | Freeze schema/version manifest. Test T10 and a changed enum; exact contract version, field, unit and coverage | Use scoped versioned catalog, schema hash, approved value maps; hold unknown currency or version | Wrong approved metadata shared by both paths |
| N3 | T1/T2/T5/T6/T7/T8/T9. Compare independently labeled cohort, denominator, date, unit and grain | Require resolved typed contract; route material disagreements to owner | Reviewer may share initial business assumption |
| N4 | Compare same T4 candidates with/without gate. Report prevented wrong releases and deferred correct queries | Compile fixed contract from vetted templates. Repairs may change syntax within same contract; budget two | Valid unseen shapes held; wrong contract still compiles |
| N5 | Test well-formed permitted SELECT, malformed action envelope and structured disallowed actions. Track missed denies and false holds | Validate schema and parse the supported dialect; deny outside allowlist; never repair a forbidden action into compliance | Parser/compiler defect; limited SQL coverage |
| N6 | X1–X3 split permission and permitted aggregate. Exercise structured negative and authorized roles, and assert prohibited effects absent | Authorize on safe views and vetted templates using read-only credentials and explicit aggregate/redaction policy | Small cohorts and differencing; role drift; prototype does not demonstrate complete enforcement |
| N7 | Check snapshot hash and named cutoff; inject timeout, row-budget exhaustion, legitimate empty result. Count labeled outcomes | Read-only immutable approved snapshot; cap time/rows; treat partial output as failure; return typed error | Workload spikes or approved stale data |
| N8 | T4 variants, T6 valid zeros and count/status reconciliation; detected wrong candidates and false holds | Metric-specific count/total checks and release hold when reconciliation unavailable; generic flags trigger review | Same wrong definition can satisfy multiple checks |
| N9 | Compare structured value, numerator/denominator, unit, date, caveat, action to reference. Human-review wording | Deterministic rendering from checked fields, redacted audit records, aggregate-only response, queue deferrals | Misinterpretation outside intended workflow; leakage via repeated requests |

## C. Monitoring and escalation

Thresholds are proposed stop or review criteria. Counts, coverage and outcomes
require separately reviewed denominators. Start in shadow mode with 100%
review and track analyst minutes before considering a wider use.

| Node | Signal and collection | Trigger and rationale | Owner and response |
|---|---|---|---|
| N1 | Live route/action and required-field flags. Weekly labeled clarification quality | Any release with unresolved material field; threshold enforces contract | Portfolio risk owner pauses metric and relabels examples |
| N2 | Live snapshot/schema/catalog hashes per trace. Daily version register | Any unknown version or unapproved unit; even one invalidates lineage | Data owner holds route, reconciles contract and reruns cases |
| N3 | Live contract ID and missing fields. Post-hoc contract/output comparisons | One material intent error; analyst decision is affected | Metric owner corrects definition; independent validation checks variants |
| N4 | Live model revision, prompt hash, attempt count, edit classification and timing | More than two rewrites is a hard stop. Review workload when at least 10 of the latest 50 repair-enabled requests retry. The fixed compiler has no retry path | Application owner holds beyond budget; reviews logs, cost and changes |
| N5 | Live parse/action blocks; reason codes by template | Any nonapproved action past N5 opens an incident; next layer contains | Application owner isolates release route and checks statement classifier |
| N6 | Live denied permission/intent, identity scope, policy revision; post-hoc disclosure incident records | Any confirmed disclosure or prohibited operation pauses access immediately | Security/data owner revokes capability, investigates and demands replay |
| N7 | Live execution result/time, row cap, snapshot ID and partial result bit | Local limit of two seconds for SQL plus reconciliation and one aggregate row. Revalidate any higher trial limit. Any incomplete release halts metric | Application owner holds result and tests load/limits before restart |
| N8 | Live reconciliation deltas and holds. Post-hoc independent numeric review | Any T4 grain/eligibility violation or confirmed material wrong release halts metric | Portfolio risk owner traces N2–N8 and expands holdout |
| N9 | Live action and approved template/release fields. Post-hoc review of material wrong releases, coverage, review time | One material wrong release or disclosure pauses route. >10 minutes average review over 30 answerable shadow requests triggers capacity review | Independent validation owns restart recommendation; analyst lead manages queue |

Keep only redacted operational evidence. In an expanded trial, review every
alert, each new or changed metric, and 10% of routine outputs by metric and
week (at least 10 if available). Revalidate on material changes.
