# ORIE 5255 requirement map

| Rubric criterion | Evidence |
|---|---|
| Scope (10) | Report §1. Single-turn analyst triage on a versioned, approved financial snapshot. Limits and decision rights are explicit |
| Architecture (15) | Report §§3–4 and appendix. Nine-node flow, repair branch and T4 end-to-end trace |
| Failure propagation (15) | Report §4 and matrix A. Causes, propagation, severity and business impact for each node |
| Offline evaluation (15) | Report §§2, 5–7 and matrix B. 19 cases, 456 archived runs, independent recomputation, benchmark audit, release metrics and blind-review plan |
| Online guardrails (10) | Report §10 and matrix B. Preventive, detective and corrective controls, owners and limits |
| Monitoring (10) | Report §11 and matrix C. Live operational telemetry and independent outcome review with triggers and responses |
| Literature and standards (10) | Report §§2, 5, 7, 9–12 and references. Benchmark, testing, architecture, audit and governance compared |
| Contributions (10) | Report §§8–9. T4 same-candidate replay and fixture results, false holds and limitations |
| Clarity (5) | English report and timed editable slides with speaker notes |

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
