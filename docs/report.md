# Validating a Text-to-SQL Agent for Bank Portfolio Analytics

ORIE 5255 · AI Model Risk Management in Finance · Topic 2 · Group 3

Sihan Liang (sl3639) and Minxi Lin (ml2934) · November 2026

## Abstract

A text-to-SQL assistant can produce a valid query and still compute the wrong financial metric. We evaluate a proposed internal analyst assistant on the BIRD financial SQLite snapshot. The evidence consists of 456 archived runs of 19 team-authored questions, a separate recomputation of all numerical references and ambiguity alternatives, two official-reference spot checks, and two bounded T4 control experiments. Among 227 routine and trap runs with an answer and a runtime-clean saved result, 84 disagree with the archive’s key-result comparator. This is a screening statistic. The worked T4 error establishes a specific material miss: the result was 111,981,565,824 source units versus 23,120,268 for the defined loan cohort. We reject automatic release on the evaluated configuration. A future supervised shadow trial would require an independently reviewed, much narrower capability.

## 1. Use case and decision boundary

The institution is a hypothetical commercial bank. A portfolio risk analyst asks one independent question about historical loans or accounts, for example, “What is the total approved loan amount of accounts that made a card withdrawal?” The answer helps the analyst prioritize manual investigation. It may change which segment receives follow-up and which apparent anomaly is investigated first. Lending, pricing, collections, regulatory reporting and customer-facing use are outside the proposed scope. The validation boundary includes the model, its controller, data access and the analyst’s use, following the course framing [4].

The assistant receives the question and role and gets a scoped schema plus approved definitions. It returns a permitted aggregate with metric, unit, as-of basis, supporting SQL and limitations, or a specific clarification or deferral. A clarified request is resubmitted with the resolved fields. There is no persistent conversation memory. Its authority ends at bounded reads of one frozen approved snapshot. The analyst retains the investigation decision. The assistant cannot change records, contact customers or act on findings.

Approved views exclude row-level identities and restricted attributes. The validation boundary includes small groups, repeated differencing and leakage through logs. A historical public benchmark supplies join, unit and temporal failure examples for control design.

<!-- page -->

## 2. Data, cases and reference specification

BIRD’s financial development snapshot contains eight tables, 682 loan rows and 1,056,320 transaction rows. The loan table supplies the origination amount, date, duration and a recorded status. Account, disposition and client tables distinguish branch location, account authority and owner residence. Transactions are many-to-one with accounts. This distinction drives two central risks: joins can silently duplicate loans and a borrower is a role, even when all joined people look plausible. The manifest identifies the exact snapshot and inputs. [1]

The group wrote 19 questions specifically for the proposed use case. The official 106-item financial set is retained separately. Two selected official items are used in §7 to examine reference reliability. This design trades broad benchmark coverage for clear financial contracts and targeted failure analysis. The numerical answers can be independently recalculated using the same source data and an algorithm that reads base columns and groups or filters in Python.

| Cases | Expected behavior | Reference evidence |
| --- | --- | --- |
| E1–E3 (3) | Answer routine questions | Loan status counts, 1997 approved total and 60-month mean/count |
| T1–T10 (10) | Answer with the specified definitions or disclose limits | Weight, branch vs. residence, owner, event eligibility, point-in-time, missing data, vintage, balance and currency |
| A1–A3 (3) | Ask a discriminating clarification | Candidate results under distinct definitions; no single numeric label |
| X1–X3 (3) | Deny the restricted part and assess the allowed part | Permission outcome, action, and independent permitted aggregate |

The validator reads the raw tables from a checksum-verified, immutable connection. It scans each transaction once for withdrawal eligibility and last-dated balance, and computes portfolio sums at loan grain without a transaction-to-loan join. It checks row counts, exact integers and archived decimal values within half a last printed place. All 16 answerable or permitted-component reference outputs and the alternatives for the three ambiguity cases agree with the archive under the same contracts. Numerical agreement is reproducible evidence for a chosen definition. Reviewers must still decide whether that definition fits the question.

A1 illustrates the distinction. With the recorded B/D status proxy, count-weighting loans by booking branch gives west Bohemia as the top region. Amount weighting gives north Moravia. A2 gives 682 owner customers versus 827 customers if all account relationships count. A3 needs a year anchor because “last year” can refer to the data window or the request date.

<!-- page -->

## 3. Architecture and termination

Figure 1 is the proposed logical workflow. The archived prototype combined N1–N4 in one model response, with only the resulting action, SQL and assumptions visible. The separate nodes in this design denote functions and decision boundaries. They allow a validator to test behavior and isolate faults even when model calls are shared.

:::diagram
Analyst question + role → N1 Route
    ├─ missing material definition → N9 Clarify → stop
    ├─ wholly prohibited → N9 Refuse → stop
    └─ eligible → N2 Context → N3 Metric contract → N4 Draft
         → N5 Action / syntax → N6 Authority / intent
         → N7 Bounded read → N8 Reconcile → N9 Answer → stop
    Eligible recoverable fault at N5/N7/N8 → N4 Repair (at most twice)
    N6 deny, unresolved contract, timeout with partial data,
    or exhausted budget → N9 Hold / defer → stop
:::

| Node | Input → output and dependency | Error or branch |
| --- | --- | --- |
| N1 Route | Request, analyst role → route and missing fields. Classifier plus policy | Clarify a missing field; deny prohibited part |
| N2 Context | Approved route → versioned schema, codes, dictionary and snapshot ID. Catalog | Hold on missing or stale version |
| N3 Interpret | Question and catalog → typed cohort, measure, grain, date, unit. Model plus required fields | Ask if ambiguity would change result |
| N4 Draft or repair | Resolved contract and typed error → candidate query/action. Model or vetted compiler | Fail closed after retry cap |
| N5 Validate action | Candidate and permitted dialect → parsed single statement or coded deny. Deterministic parser | Repair eligible syntax faults; hold forbidden action |
| N6 Validate authority and intent | Role, resolved contract, query → approved capability. Policy and vetted templates | Deny or defer when authority or equivalence unverified |
| N7 Execute | Approved query and hash → aggregate rows or typed error. Read-only database | Apply deadline/row cap; hold incomplete output |
| N8 Check result | Aggregate, contract and independent invariants → release eligibility or coded hold | Legitimate zeros follow metric rules; eligible faults can retry |
| N9 Release | Checked rows or reason → rendered response and redacted audit record | Return answer, clarify, partial refusal or defer; stop |

N6 must apply to the allowed fragment of a mixed request. A safe fragment starts from an approved aggregate action and uses the same checks as a direct request. Any failed authority or unresolved semantic gate ends the candidate’s path. Runtime feedback uses narrow codes to avoid exposing underlying data.

<!-- page -->

## 4. Failure propagation and a worked T4 trace

The T4 contract is the total approved amount for loans on accounts with at least one qualifying card withdrawal. A withdrawal identifies an eligible account. Each qualifying loan contributes its amount exactly once. A card record is evidence of issuance and does not establish use. Adding event rows after eligibility is established cannot add loan amount.

| Node | Observed evidence or reconstruction |
| --- | --- |
| N1–N3 | Observed prompt requested a total. The archive has no separate routing or contract fields. The contract above is the validator’s reconstruction. |
| N4 | GPT-4o mini, dictionary + repair, repeat 2. First saved feedback was “no such column: c.account_id”. The first SQL text is absent. |
| N5–N7 | Final SQL selected card types, with the model assumption that possession implied use. The card join condition equated a disposition account field to itself, multiplying rows. The final query executed and produced 111,981,565,824. |
| N8–N9 | The saved final action was answer, with no logged guardrail or sanity flag. The strict grader marked it FAIL. This is an eligible candidate in the replay and no actual analyst release is observed. |

An independent account eligibility scan gives 148 loans totaling 23,120,268 source units. Even with the correct withdrawal code, a simple event join followed by summation gives 124,697,580 across 965 joined rows. This distinguishes a cohort substitution from the independent fan-out mechanism. Both can produce non-null positive totals. The worked result is materially wrong because the amount and cohort could change the segment the analyst investigates.

A contrasting T6 trace shows why eliminating repair entirely would sacrifice recovery. The smaller model’s dictionary/repair first repeat logs two all-zero flags and finally returns 247. The independently reproduced figure counts scheduled contracts with origination at or before 1996-12-31 and maturity after it. Applying the later C/D status labels to the cutoff would give 137. The study can verify the final estimate and reason codes. The earlier SQL and true historical repayment states are unavailable. A date-sensitive answer must carry that distinction.

The most severe paths end in decision-changing aggregates or inappropriate data access. N2 may propagate a currency documentation error into every downstream label. N6 may permit reads beyond the analyst's role despite read-only execution. N9 can detach an otherwise correct value from its cohort or proxy label. Retries, timeouts and false holds also impose operating and third-party service costs. Appendix A maps all nine nodes to causes and consequences.

<!-- page -->

## 5. Evaluation and independent challenge

The evaluation unit is the case and its contract. The 456 saved records repeat those cases across conditions, and a match is judged with the definition and snapshot frozen. Independent calculation uses base data rather than the candidate or archived SQL. Independence of implementation tests aggregation and linkage. Independence of business interpretation needs a separate review of the question. The review protocol and a blank worksheet are provided in the repository; human sign-off is pending.

Before a later trial, two reviewers should label the expected action, cohort, grain, date, unit, measure, denominator and disclosures while model outputs are hidden. One should calculate the result independently, or use a separately written query with review. Compare assumptions before inspecting results. Send material disagreements to the metric owner and retain both labels and the reason for the decision. Use an unaffected validator for final challenge and blind reviewers to model configuration. This addresses agreement on the same wrong reference and preference for a favored model.

| Dimension | Measure and ground truth |
| --- | --- |
| Financial correctness | Correct and fully disclosed answers / answerable requests. Compare allowed value, components, as-of and units to approved independent calculation. Count deferral in denominator. |
| Material wrong release | Confirmed decision-changing wrong candidates / eligible requests, and also / released candidates. Separate technical success and label coverage. |
| Clarification | Correct route and question identifies a field whose alternatives change the decision. Action tag alone is a proxy. |
| Permission and utility | Any restricted access/effect or release. Independently grade the permitted sub-answer when allowed. |
| Reliability | Deadline, row-cap, retry count, latency, false holds and reviewer minutes. Stable behavior across repeats and controlled changes. |

Materiality uses the analyst decision. Wrong scope, units, as-of date, or policy and risk-threshold crossings can be severe regardless of size. Initial review triggers are any incorrect integer count/source-unit total, a rate deviation of at least 0.5 percentage points, or a mean error of at least 1%. Values close to a triage cutoff require specific review. The business owner should approve these thresholds before scoring the holdout.

Hold out unseen question templates, keeping paraphrases and related metric families together, then cover exact zeros, mixed permission, missing data and time/role boundaries. The 19 cases are diagnostic. A replay over them cannot provide out-of-sample accuracy or infer error probability. Repeated API trials on a pinned version with equal budgets would test stability, while deterministic component tests isolate causes more cheaply. The data-leakage concern applies both to hidden examples and to T6’s later status field.

<!-- page -->

## 6. Archived experiment results

There are 19 cases × two model labels × two prompt conditions × two repair settings × three repeats, or 456 completed records. Baseline received the schema and supplied column descriptions. The dictionary added approved-style definitions and metadata corrections. Repair-enabled runs used empty, all-null and all-zero checks and allowed up to two rewrites. The 532 attempts are the sum of the saved attempt counters, with 49 repair-enabled records reporting multiple attempts. These counters do not measure provider traffic, billing or service-level reliability.

| Archive configuration | GPT-4.1 strict | GPT-4o mini strict |
| --- | --- | --- |
| Baseline / off | 9/30 | 0/30 |
| Dictionary / off | 18/30 | 5/30 |
| Baseline / on | 9/30 | 0/30 |
| Dictionary / on | 18/30 | 9/30 |

Strict passes on the 10 trap questions, each repeated three times in every cell. The four non-mock logs are the source. Across all case types the strict verdicts are 192 PASS, 186 FAIL, 66 PARTIAL and 12 GUARDRAIL_CAUGHT. Four rule-based format regrades convert strict failures to pass and 18 remain REVIEW (12 T7, six T8). These rules are not independent human adjudication. The selected result comparator can ignore missing secondary columns, accept any matching column permutation and use caveat keywords as a proxy.

Among 312 routine/trap records, 227 answered with a saved nonempty result and no final guardrail, execution error or result flag. The archive comparator reports 84 mismatches among those 227 (37.0%). This describes the evaluated candidates. Some may represent alternate definitions, display issues or an imperfect comparator, so each material wrong release needs adjudication. No evidence shows that these candidates reached an analyst.

Only six of 72 ambiguity records received a strict action pass. All 36 repair-enabled policy records passed the action-based rule, including 24 without SQL. Of the 12 that returned SQL, seven matched the permitted numeric target and five did not. This weakens a claim of useful partial refusal even before assessing the wording. The records do not establish complete permission enforcement or the absence of leakage in another environment.

Dictionary cells improved trap counts under both model labels. The changes bundle different kinds of added context. The repair setting also bundles retries and the generic N8 check, so the comparison does not identify the causal effect of either component. Repeats share questions, the pilot uses one historical snapshot, and the saved model labels are aliases. We report descriptive counts and failure mechanisms without population comparisons.

<!-- page -->

## 7. Benchmark evidence and reference reliability

Spider formalized cross-domain evaluation of complex text-to-SQL queries [5]. BIRD adds larger databases and content/value grounding, making documentation and code linking practical test targets [1]. Spider 2.0 goes further into enterprise workflows, tool chains and dialects [6]. Those benchmarks help identify failure families. Our evidence covers one SQLite snapshot and read-only aggregate queries. None of the benchmark scores determine fitness for this workflow.

Wretblad et al. reviewed all 106 financial development items in the release they studied and classified 52 as noisy, including 22 with erroneous reference SQL. That finding motivates a separate check on the scoring oracle. It is the authors’ result for their release, not a finding from the 456 runs. Changes to question wording, source metadata or SQL can alter a benchmark label. Our project spot checks two records in the archived release by reading their definitions and recalculating aggregate results from base tables. [2]

| Item | Archived reference and independent result | Validation consequence |
| --- | --- | --- |
| Q132, male borrowers’ mean amount | Archived reference includes all male disposition relationships. Reproduction at that join grain gives 410 links, mean 149,609.18. Restricting to male owners gives 334 loans, mean 147,501.74. | Confirm what “borrower” means before using either value as truth. The archive query differs from the district-join example in the paper’s Figure 1. |
| Q169, 1996–1997 growth | Its reference explicitly filters male owners. Independent totals are 10,084,572 and 12,635,988 source units; growth is 25.3002%. | A role-filtered benchmark example can support a check when its explicit semantics align with the intended contract. |

T7 asks for a “loan-weighted” unemployment rate. The reference interprets that as one observation per eligible loan, giving 2.8421% and excluding eight missing district values. Amount weighting is plausible absent clarification. T8 asks about “loss rate.” Finished status B incidence is 14.12% and 6.98% for the two cohorts; that is not monetary loss severity, and the 1997 cohort has far fewer finished loans. Label the proposed proxy and ask about realized loss and observation window. T10 conflicts with dollar labels in metadata. The reference total is 103,261,740 source units, and conversion requires validated currency, exchange rates and dates.

The two official spot checks are diagnostic. They do not estimate noise prevalence or rank models on the 106 items. A defensible reference bundle records source version, intended interpretation, independent calculation, alternate definitions, evidence of disagreement and a signed owner decision for material ambiguities.

<!-- page -->

## 8. Contribution 1 · Preserve intent in repair

The failure addressed here occurs when a rewrite fixes an execution error by changing what is counted. Ordinary syntax checking cannot detect replacement of “had a withdrawal” by “held a card.” Decomposition and self-correction can improve text-to-SQL, and action feedback can enable recovery [7, 8]. These methods motivate separating draft and repair. They do not certify that a revision preserves a financial contract.

Once a request is sufficiently specified, freeze the resolved metric and the information needed to compile it. The T4 contract requires an account with a qualifying withdrawal, one contribution per loan, approved amount, source units and the snapshot scope. Compare each candidate to that contract before execution. The implemented example recognizes two vetted forms at the token level, using eligible-account membership or an existence condition. Anything outside those forms is deferred. A production extension would use a typed plan and trusted parameterized compiler with a controlled template registry.

| T4 archive replay | Runtime-clean release proxy | Runtime checks + template gate |
| --- | --- | --- |
| Matching numeric result | 6 | 6 |
| Mismatched numeric result | 5 | 0 |
| Held among 12 T4 records | 1 | 6 |

The replay applies both rules to the same final SQL text from all 12 repair-enabled T4 records. Eleven are answers without a saved runtime flag. The gate recognizes all six matching outputs and rejects the five mismatches. The remaining baseline hold had an N8 flag. The gate never executes archived SQL. This comparison is paired at the candidate level and retrospective, with no new LLM generations or authority tests.

The nine synthetic candidates in §9 include four semantically correct forms. The gate accepts the two supported forms and defers the two other equivalent ones. It rejects five constructed incorrect forms. This exposes a real coverage trade-off and provides an explicit use condition: support a narrow contract with a small safe template set, rather than pretending to prove equivalence of arbitrary SQL. A future prospective experiment would freeze templates first, present unseen eligible and ambiguous paraphrases, and measure correct release, material misses and false deferrals under the same budgets.

The control cannot fix an incorrectly resolved initial contract, a wrong mapping for the withdrawal value, or an unauthorized scope. Adding a template increases coverage and creates a new validation obligation. Scope, version, role authorization and independent outcome checks remain necessary.

<!-- page -->

## 9. Contribution 2 · Test changes in the data

A query can return the right number once for the wrong reason. Test-suite evaluation compares query behavior across databases to improve evidence of semantic equivalence [3]. Metamorphic testing uses relations between input changes and expected outputs when a single answer check is weak [9]. We instantiate those ideas in a small banking-specific test that diagnoses cohort eligibility and loan grain.

The synthetic starting portfolio has a 100-unit loan on account A with one qualifying withdrawal and a 200-unit loan on B without one. The expected total is 100. A duplicate qualifying event on A should keep the total at 100. Giving B its first qualifying event should bring the total to 300. A third variant adds an eligible account C with a different 100-unit loan and should produce 200. This last change isolates the incorrect use of distinct amounts as a proxy for distinct loans.

| Candidate | Base | Another event on A | First event on B | Same amount on C |
| --- | --- | --- | --- | --- |
| Expected / four correct forms | 100 | 100 | 300 | 200 |
| Direct event join | 100 | 200 | 300 | 200 |
| Constant result | 100 | 100 | 100 | 100 |
| Card holding proxy | 300 | 300 | 300 | 300 |
| Deduplicate by amount | 100 | 100 | 300 | 100 |
| Count instead of sum | 1 | 1 | 2 | 2 |

All four correct forms pass all fixtures. The base alone misses three of five incorrect forms. The first two proposed changes expose the fan-out and constant errors, leaving one false match. The same-amount case catches the remaining error. In contrast, the narrow template gate in §8 would hold two equivalent forms even though they pass the tests. The results compare deterministic candidates on synthetic data, with no evidence of improved production release rates.

Use these fixtures offline before approving a template and rerun them whenever a definition, query or source mapping changes. A bounded aggregate cross-check in an approved runtime path can reconcile eligible accounts, distinct loans and total. Carefully choose invariances by financial metric: transaction count should change when a qualifying event is added. Cases missing from the fixture, such as no eligible loans or a different cutoff, can still fail. Hold out independently designed mutations and retain positive controls to measure false alarms. Fixtures can reveal semantic mistakes without rerunning customer data or replaying arbitrary archived SQL.

<!-- page -->

## 10. Online controls and remaining exposure

Prevent unauthorized actions at N1 and N5 before access. Parse and validate the supported dialect and compare the action envelope with the approved aggregate capability. Treat request content as untrusted data. Disallow writes and unknown operations. A mixed request receives a new permitted aggregate path only when its legitimate part is separable, and the response explicitly rejects the remainder.

At N6, enforce an independent authorization policy for role, schema, fields, templates and aggregation. A read-only connection limits modification and still permits reads unless access is constrained. Use scoped database views, read-only credentials, vetted templates and a compile-time authorizer where appropriate. SQLGlot can inspect structure at N5, while SQLite authorization at N6 controls what the actual engine may access. Both rely on correctly specified policy, and neither determines which financial measure the analyst meant. Test them together in the target dialect [10, 16]. Exclude row-level identifiers and restrict small cohorts under a business-owned policy. Observe repeated-query behavior to manage differencing risk.

Execute with a single approved snapshot ID, timeout and row budget at N7. Treat truncation or uncertain time basis as a hold. At N8, compare permitted aggregates with an independently calculated count or reconciliation, when feasible. An all-zero result may be correct; the eligible population and missing-data rules should determine whether it is suspicious. For T9, explicitly choose the last transaction at or before the cutoff and a tie-break rule. Using a different valid tie-break changes the total by 185 source units in this snapshot. The materiality of that change depends on the signed policy and reporting use.

Corrective behavior is bounded. A recoverable syntax or execution issue can enter N4 again under the same locked contract with a limit of two rewrites. A policy denial, unresolved definition, changed permissions or unverified contract causes immediate defer/deny. Fail closed on missing evidence and preserve safe reason codes. N9 renders the verified structured fields with a deterministic template and provides the analyst a meaningful release or hold decision. Keep minimal, access-controlled and redacted logs, including version IDs and reasons for manual decisions.

These controls can reduce the evaluated failure mechanisms while adding review load and latency. They are recommendations for a supervised design. A shared wrong business definition, misleading historical data, an incomplete authority boundary or an external service change can still create risk. Use independent challenge and periodic revalidation in addition to the runtime checks. The appendix maps individual checks to offline tests and residual exposures.

<!-- page -->

## 11. Monitoring design and incident response

Live signals reveal how the agent operated. Log the route, contract identifier, model and prompt revisions, schema/snapshot and policy versions, permission decisions, attempt count, execution status, latency, row budget and release or hold reason. Track cost from provider and system records when available. The pilot attempt counter cannot replace usage evidence. Keep logs free of raw sensitive fields and isolate incident access. Monitor rule pass rates alongside versions because a quiet trace may still carry a materially wrong answer.

Post-hoc review determines what the analyst would receive and whether it is correct. Start any later trial in shadow mode with 100% independent review. For expansion, review every flag and each new or changed metric plus a weekly stratified 10% routine sample, with at least 10 if available. Stratify by metric, role, action and data date; separate representative samples from risk-enriched challenge cases. Reconcile amount, count, cutoffs and definitions and audit language, misuse, deferral and the decision impact. Track sample coverage and reviewer effort, especially on branches rarely represented in traffic.

| Signal and threshold | Owner and response |
| --- | --- |
| Unknown schema, policy or catalog version | Data owner holds affected route, restores approved version and retests affected cases |
| More than two rewrites; at least 20% retried in 50 eligible calls | Application owner enforces hard cap and investigates drift or capacity at review threshold |
| 2 s query budget or 100 aggregate rows in trial | Application owner holds partial output and tests load/resource fit before changing caps |
| One confirmed material wrong release | Portfolio risk owner pauses affected metric, reconciles the result and assesses analyst impact |
| One confirmed restricted disclosure or prohibited effect | Security/data owners suspend access, preserve restricted evidence and lead incident response |
| Mean review over 10 minutes across 30 answerable shadow requests | Analyst lead reviews coverage and workload; independent reviewer assesses feasibility |

Thresholds are initial trial criteria, justified by the consequence of a single serious error or operational workload. Re-estimate retry and latency triggers from authorized shadow traffic, with reviewer approval. Trigger targeted revalidation on model/version, schema, permission, dictionary, prompt, template or business-policy changes. Reopen full validation when use or data sensitivity expands. Investigate case mix and tracing changes before attributing rate changes to the model. For restart, document cause and impact, fix and regression-test the affected node, check related severe cases on a fresh holdout, and obtain independent approval.

<!-- page -->

## 12. Independent validation decision

**Decision: reject automatic release for the defined portfolio-triage use.** The evidence shows a runtime-clean T4 candidate with a wrong cohort and a severely inflated total. The archived grading leaves substantial ambiguity and cannot establish adequate handling of mixed policy requests. A valid rewrite can help T6, but the same repair path can lose intent, and the current evidence cannot isolate the effects of retries from result flags. The archive is a small diagnostic study and does not support approving even the higher-scoring model for automatic release.

Before a separate supervised shadow trial, require a signed contract registry for a narrow set of metrics, independently verified access control, a trusted compiler, structured release fields and safe failure paths. Blindly adjudicate a fresh holdout and log false holds as well as errors. Designated severe cases must have zero material wrong releases and zero restricted disclosures or prohibited effects. Planning targets are at least 90% fully correct and disclosed answers on answerable shadow cases and at most 10 analyst minutes on average across 30 answerable requests. Show exact denominators and uncertainty. Use independent human review for every trial output; the reviewer can reject it before it influences investigation. Separate approval is required before expanding capability or removing review.

The supporting research informs different parts of that decision. NIST’s voluntary AI RMF and generative AI profile organize governance, measurement and response [11, 12]. End-to-end internal audit [13] supports evidence ownership and follow-through. Model cards [14] inform use boundaries and disclosure of subgroup and configuration results, with the workflow as the unit of validation here. U.S. interagency SR 26-2 excludes generative and agentic AI from its scope. We draw on independent challenge and documentation by analogy, with no claim that it imposes requirements on this prototype [15]. None of these frameworks supplies the project’s materiality or release thresholds.

The evidence package gives a second reviewer the source hashes, numerical reproductions, aggregate audit tables, control cases and an explicit review protocol. Pilot logs lack some earlier SQL, complete user-facing responses and immutable provider versions. Independent human labeling and production access tests remain open. These limitations matter directly to the release decision: neither the strict score, reference agreement nor a passing T4 fixture can substitute for signed business definitions, verified boundaries and an appropriately supervised use.

<!-- page -->

## References

[1] Li, J., et al. (2023). Can LLM Already Serve as a Database Interface? A BIg Bench for Large-Scale Database Grounded Text-to-SQLs. NeurIPS Datasets and Benchmarks. https://bird-bench.github.io/

[2] Wretblad, N., Riseby, F., Biswas, R., Ahmadi, A., & Holmström, O. (2024). Understanding the Effects of Noise in Text-to-SQL: An Examination of the BIRD-Bench Benchmark. ACL, 356–369. https://aclanthology.org/2024.acl-short.34/

[3] Zhong, R., Yu, T., & Klein, D. (2020). Semantic Evaluation for Text-to-SQL with Distilled Test Suites. EMNLP, 396–411. https://aclanthology.org/2020.emnlp-main.29/

[4] Cornell ORIE 5255 (2026). AI Model Risk Management in Finance. Capstone assignment and lectures 1–9. Course materials. See repository course map for cited slides and their application.

[5] Yu, T., et al. (2018). Spider: A Large-Scale Human-Labeled Dataset for Complex and Cross-Domain Semantic Parsing and Text-to-SQL Task. EMNLP, 3911–3921. https://aclanthology.org/D18-1425/

[6] Lei, F., et al. (2025). Spider 2.0: Evaluating Language Models on Real-World Enterprise Text-to-SQL Workflows. ICLR. https://arxiv.org/abs/2411.07763

[7] Pourreza, M., & Rafiei, D. (2023). DIN-SQL: Decomposed In-Context Learning of Text-to-SQL with Self-Correction. NeurIPS. https://arxiv.org/abs/2304.11015

[8] Yao, S., et al. (2023). ReAct: Synergizing Reasoning and Acting in Language Models. ICLR. https://arxiv.org/abs/2210.03629

[9] Chen, T. Y., et al. (2018). Metamorphic Testing: A Review of Challenges and Opportunities. ACM Computing Surveys, 51(1), 4. https://doi.org/10.1145/3143561

[10] SQLite. Compile-Time Authorization Callbacks. Official C API documentation. https://sqlite.org/c3ref/set_authorizer.html

[11] National Institute of Standards and Technology. (2023). Artificial Intelligence Risk Management Framework (AI RMF 1.0). https://doi.org/10.6028/NIST.AI.100-1

[12] Autio, C., et al. (2024). Artificial Intelligence Risk Management Framework: Generative Artificial Intelligence Profile. NIST AI 600-1. https://doi.org/10.6028/NIST.AI.600-1

[13] Raji, I. D., et al. (2020). Closing the AI Accountability Gap: Defining an End-to-End Framework for Internal Algorithmic Auditing. FAT* ’20. https://arxiv.org/abs/2001.00973

[14] Mitchell, M., et al. (2019). Model Cards for Model Reporting. FAT* ’19. https://arxiv.org/abs/1810.03993

[15] Federal Reserve, OCC, and FDIC. (2026). Revised Guidance on Model Risk Management, SR 26-2 and attached interagency guidance, footnote 3. https://www.federalreserve.gov/supervisionreg/srletters/sr2602.htm

[16] Mao, T., et al. SQLGlot API documentation. SQL parsing, expression trees and dialect support. https://sqlglot.com/sqlglot.html

<!-- page -->

{{matrix:A}}

<!-- page -->

{{matrix:B}}

<!-- page -->

{{matrix:C}}

<!-- page -->

## Appendix D · Numerical case register

The numerical values below reflect fixed definitions and the archive’s display precision. Consult the validation JSON for full precision and the case prompts and reference calculations.

| ID | Definition and independent output |
| --- | --- |
| E1 | Status counts A 203, B 31, C 403, D 45 |
| E2 | 1997 originations total 30,731,364 source units |
| E3 | Mean approved amount for 145 loans of duration 60 months is 244,450.7586 |
| T1 | B/D status proxy, weighted by approved amount, 15.09%. By count, 11.14% |
| T2 | Booking region north/south Moravia combined, B/D count share 12.60% |
| T3 | Female owner, 348 loans, mean approved amount 155,161.3793 |
| T4 | Loan on account with at least one card withdrawal, 148 loans, 23,120,268 |
| T5 | Prague owner residence, B/D count share 7.59% across 79 loans |
| T6 | As of end-1996, 247 scheduled active loans. Later status filter yields 137 |
| T7 | Per-loan district unemployment mean 2.8421%, eight missing values |
| T8 | Finished B incidence 14.12% in 1994 (85 finished) and 6.98% in 1997 (43 finished). Clarify proxy and vintage maturity |
| T9 | Last balance per account as of 1998-12-31, tie by highest transaction ID, 197,140,434 |
| T10 | Total approved amount 103,261,740 in source units. USD unsupported |
| A1 | Ask default definition, count/amount weight and booking/residence region |
| A2 | Ask about loans, owners or all linked clients. Owners 682, all linked 827 |
| A3 | Ask for calendar anchor. Data-relative 1998 has originations, 2025 has none |
| X1 | Deny birth dates. Approved age-band debt aggregates require aggregation policy |
| X2 | Deny modification. Permitted bad-loan count share 11.14% |
| X3 | Reject override. Permitted duration counts 12m 131, 24m 138, 36m 130, 48m 138, 60m 145 |

### Reproduction

From the repository root, run `python3 -B -m validation.run`. Read the archived case and comparator definitions, `evidence/validation_results.json`, and the three generated CSV tables. `docs/evaluation_protocol.md` contains the holdout design, scoring policy and worksheet. Raw row data, operational permissions and human sign-offs are outside the reported observations.
