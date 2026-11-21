# ORIE 5255 requirement map

The course specifies a 12–15-page paper before references and appendices, at least 12 substantive references, and a 12-minute presentation with questions. The two source documents used for the final review are preserved byte for byte. Their checksums are recorded separately from the frozen pilot manifest. [Course assignment](../archive/course_sources/Cornell_AI_MRM_Capstone.docx) · [Group 3 proposal](../archive/course_sources/project%20proposal.docx) · [Source checksums](../archive/course_sources/SHA256SUMS)

| Rubric criterion | Evidence |
|---|---|
| Scope (10) | Report §1. Single-turn analyst triage on a versioned, approved financial snapshot. Limits and decision rights are explicit |
| Architecture (15) | Report §§3–4 and appendix. Nine-node flow, repair branch and T4 end-to-end trace |
| Failure propagation (15) | Report §4 and matrix A. Causes, propagation, severity and business impact for each node |
| Offline evaluation (15) | Report §§2, 5–7 and matrix B. 19 cases, 456 archived runs, separate outcome denominators, T4 scalar audit, 106-item benchmark replication, 19-question replay, 30 structured technical cases and a separate human holdout plan |
| Online guardrails (10) | Report §10 and matrix B. Restricted local compiler with 35 measures, a two-second calculation budget and a single aggregate row, plus proposed bank controls |
| Monitoring (10) | Report §11 and matrix C. Telemetry, outcome review, prospective intake/ledger scorer, incident triggers and responses |
| Literature and standards (10) | Report §§2, 5, 7, 9–12 and references. Benchmark, testing, architecture, audit and governance compared |
| Contributions (10) | Report §§8–9. T4 same-candidate replay and fixture results, false holds and limitations |
| Clarity (5) | English report and timed editable slides with speaker notes |

## Proposal commitments and evidence

| Commitment in the submitted proposal | What can be checked | Evidence still needed |
|---|---|---|
| Limit the assistant to a single request, one approved snapshot and historical portfolio aggregates | The local controller executes fixed measures on the pinned database. On the 19 original questions it returned nine full answers, four partial answers and six clarifications. On 11 complete resubmissions the controller returned ten verified answers and held the request for unavailable historical repayment status. [Question replay](../evidence/question_replay.csv) · [Clarification paths](../report/evidence/clarification_paths.csv) · [Regional, owner and annual checks](../evidence/clarified_portfolio_queries.csv) | Authenticated bank roles, live access controls and analyst acceptance require testing in the target service. |
| Check portfolio definitions and reference quality before grading | The team compared 106 official IDs across four releases. For Q132, following dispositions gives 410 observations averaging 149,609.18 source units. Restricting the calculation to male owners gives 334 loans averaging 147,501.74. [Release comparison](../report/evidence/gold_release_comparison.csv) · [Owner and linked-client calculations](../evidence/validation_results.json) | A metric owner must decide which cohort fits the bank's question. Figure 2 model accuracies come from the paper. Per-item predictions for independent rescoring were unavailable in its pinned release. |
| Trace a financially wrong answer from request to release decision | The T4 pilot question specifies **card withdrawals**. Each loan on an eligible account contributes its principal once. Full-snapshot eligibility gives 148 loans. Requiring a withdrawal by approval gives 24. The verified total is 23,120,268 source units across **148 loans**. The proposal's worked example calls those 148 transactions. [Exact pilot prompt](../archive/text2sql_bird/test_suite.py) · [T4 calculations](../evidence/t4_amount_audit.csv) · [Timing comparison](../report/evidence/withdrawal_timing.json) | The first failing SQL and evidence of delivery to an analyst are missing. |
| Establish expected actions and values with outputs hidden, then retain disagreements | Thirty structured cards specify expected actions and values. A base-row calculation checks the numeric labels, and 18 disputed T7/T8 records have interpretation notes. [Case cards](../validation/challenge_cases.json) · [Interpretation review](../evidence/interpretation_review.csv) | No independently signed human holdout is available. An external reviewer must label unseen questions before inspecting their answers and retain unresolved disagreements. |
| Score material wrong releases, correct answers, disclosures and appropriate deferrals, including the permitted part of mixed requests | The pilot supplies execution and key-agreement proxies. For the 36 repair-enabled policy runs, seven permitted alternatives matched the archived key, five differed and 24 had no SQL. [Policy outcomes](../evidence/repair_policy_by_case.csv) · [Grading protocol](evaluation_protocol.md) | Missing answer and clarification text limits disclosure and deferral judgments. Observed material wrong-release and fully disclosed utility rates require adjudicated original outputs. |
| Test whether a repair preserves intent, and whether new transaction records preserve loan grain | On the same 12 repair-enabled T4 records, the gate held all five runtime-clean mismatches and retained six matches. In the synthetic test the four valid SQL forms passed the base and three variants. Every constructed faulty form failed at least once. [T4 replay](../evidence/t4_archive_replay.csv) · [Fixture outputs](../evidence/validation_results.json) | Unseen SQL and independently chosen changes to other portfolio measures are needed to estimate detection and false holds beyond T4. |
| Define hallucination, test unsupported answers and detect use of stale data | T10's unsupported USD claim can be checked against the unit and conversion evidence. A T8 explanation gives an incorrect counting rule despite a matching value. The snapshot tests exercise stale executor and cache versions, including a stale result whose number still matches. [Archived claim checks](../report/evidence/archive_diagnostics.json) · [Snapshot tests](../report/evidence/snapshot_binding.json) | Human review must establish claim-level correctness when the original text exists. A trusted data owner must certify the live snapshot's as-of date. |
| Decide on use and monitor both reliability and financial correctness | The decision withholds automatic release. The shadow protocol retains original responses, includes holds in the answerable cohort and records active review time. [Readiness record](../evidence/shadow_readiness.json) · [Intake and review protocol](evaluation_protocol.md) | The intake and review ledgers have zero observed requests. The trial has no measured review time, 30-request utility result or target-service approval. |

## Lecture applications

| Course slide deck | Application to this project |
|---|---|
| `AI_MRM_2026.pptx`, slide 21 | Validate the model, database, controller, UI, and analyst workflow as one decision boundary |
| `Cornell_AI_MRM_Class2_Improved_Inductive_Validation.pptx`, slides 15, 26, 47 | Treat hand-built cases and repeated runs as risk discovery, with business-specific success criteria and a separate holdout |
| `Cornell_AI_MRM_Class3.pptx`, slide 19 | Check T6 for leakage from a later snapshot into an earlier as-of answer |
| `Cornell_AI_MRM_Lecture4_final (1).pptx`, slides 39, 46, 48 | Freeze thresholds and evaluate on independent question families before approval |
| `Cornell_AI_MRM_Class5.pptx`, slides 8, 16, 22, 30, 34, 40, 45 | Use perturbations, causal traces, and separate observability from actual correctness |
| `Cornell_AI_MRM_Class6.pptx`, slides 6–7, 28, 33, 35 | Record versioned agent traces and inspect repeat variation under the same task |
| `Cornell_AI_MRM_Class7.pptx`, slides 27–30 | An answer can accurately relay a result computed for the wrong financial question |
| `Cornell_AI_MRM_Class8.pptx`, slides 24, 31, 33–37 | Model tool use, iteration and termination explicitly. Give a validator its own reference method |
| `Cornell_AI_MRM_Class9.pptx`, slides 14, 16, 19, 29 | Govern privacy and tools with enforced authority and a meaningful analyst decision |

The project archive contains the assignment and proposals. Original lecture
slides remain in the course workspace.
