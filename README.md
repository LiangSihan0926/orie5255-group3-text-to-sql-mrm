# Validating a Text-to-SQL Agent for Bank Portfolio Analytics

ORIE 5255 · Topic 2 · Group 3 · Sihan Liang (sl3639) and Minxi Lin (ml2934)

A portfolio analyst asks how much principal was approved on accounts with a card withdrawal. One archived query returned 111,981,565,824 source units. Reconstructing the accounts and counting each loan once gives 23,120,268 across 148 loans. This study traces the difference, replicates the financial subset of Wretblad et al., and tests a local controller against the same historical database.

## Final submission

- [English report, PDF](deliverables/Group_3_ORIE5255_Final_Report.pdf) and [editable LaTeX source](report/main.tex).
- [12-minute presentation with speaker notes and Q&A](deliverables/Group_3_ORIE5255_Final_Presentation.pptx).
- [Course requirements map](docs/course_mapping.md), [node-level traceability](docs/traceability.md), and [evaluation and review protocol](docs/evaluation_protocol.md).

## Run locally

The validation uses Python 3.10 or later with SQLite 3.31 or later and the standard library. Start in this directory and run the commands sequentially. The restricted executor holds a request if its calculation exceeds two seconds. Database contention can therefore change availability even on the same machine.

    python3 -B -m validation.run
    python3 -B -m validation.review_interpretations
    python3 -B -m validation.question_replay --check evidence/question_replay.csv
    python3 -B -m validation.challenge_runner --verify-oracles
    python3 -B -m validation.challenge_runner --check evidence/structured_challenge.json
    python3 -B -m unittest discover -s tests -v
    python3 -B report/verify_supplement.py
    python3 -B -m validation.shadow_score score docs/shadow_review_template.csv --intake docs/shadow_intake_template.csv --originals evidence/shadow_originals

To try the analyst entry point directly, use a supported question or list its forms.

    python3 -B -m validation.questions 'How many loans were scheduled to be active on 1996-12-31?'
    python3 -B -m validation.questions 'At the 1998-12-31 snapshot, which booking-branch region had the highest share of loans with status B or D, counting each loan once?'
    python3 -B -m validation.questions 'How many distinct owners of accounts with an originated loan appear in the 1998-12-31 snapshot?'
    python3 -B -m validation.questions 'What was the average approved loan amount in source units for loans originated in calendar year 1997?'
    python3 -B -m validation.questions 'Show the average approved loan amount by origination year in source units'
    python3 -B -m validation.questions --list
    python3 -B -m validation.shadow vintage_finished_unpaid_share --vintage 1997 --as-of 1998-12-31

The compiler accepts 35 named aggregate measures and vetted question forms. A regional ranking requires a region basis (booking branch or owner residence), a weight (loan count or approved principal) and a status proxy. The answer shows the numerator and denominator for each ranked region. Equal rates share a rank. The owner count deduplicates owners across borrowing accounts. The annual mean covers approved principal on loans originated in a requested year, or returns a breakdown for all six years from 1993 through 1998. It uses the host-supplied role, an immutable database with a pinned hash, metric-specific column permissions, fixed SQL and an independent calculation on base rows. There is no model call in this route. A recognized mixed request may receive an authorized subanswer. Unknown wording receives a hold. The original experiment, its contemporaneous instructions and source inputs are frozen for checksum verification. The commands above reproduce the study using the packaged snapshot. [Archive manifest](archive/manifest.json) · [Data attribution](data/NOTICE.md)

## Read the results

| Evidence | Observation and denominator |
| --- | --- |
| [Benchmark replication](report/README.md) | 52 of 106 official financial items carry a noise label. Comparing the authors' SQL-only corrected release with their original changes 24 of 106 reference outputs on identical database bytes. |
| [Figure 8 prediction replay](report/evidence/published_q177_replay.json) | Both illustrated Q177 queries fail as printed. After one comma is inserted in each, only the reworded-question prediction matches the three references. |
| [Withdrawal timing](report/evidence/withdrawal_timing.json) | The full-snapshot T4 cohort has 148 loans totaling 23,120,268. Only 24, totaling 3,963,600, had a recorded card withdrawal by loan approval. The data use approval date as the origination proxy. |
| [Signed closing balances](evidence/question_replay.csv) | For T9, 4,461 positive balances totaling 197,405,904 and 39 negative balances totaling −265,470 give the archived net of 197,140,434. |
| [Archived pilot](evidence/numeric_by_configuration.csv) | 19 questions repeated across configurations produced 456 runs. Of 312 routine/trap records, 227 returned a candidate with no final flag. Among those, 84 differed from the key. |
| [Pilot disclosure audit](report/evidence/pilot_disclosure_audit.csv) | Of 46 matching answers subject to a keyword rule, 17 missed it. All 47 matching results on E3, T3 and T4 saved the amount alone. |
| [Interpretation review](evidence/interpretation_review.csv) | All 12 disputed T7 results match approved-amount weighting. All six disputed T8 results match the status B/D share of all originations. Raw grades are preserved. |
| [English replay](evidence/question_replay.csv) | The 19 known original prompts produced nine answers, four partial answers and six clarifications. X1 withholds individual data and returns loan counts and approved principal by age band. Per-case checks compare values with base rows and check expected actions. |
| [English resubmissions](report/evidence/clarification_paths.csv) | After six known clarifications, ten of 11 fully specified requests gave verified answers. The snapshot could not establish actual repayment status at year-end 1996, so that request was held. |
| [Regional rankings, owners and annual means](evidence/clarified_portfolio_queries.csv) | Twenty queries produce 109 evidence rows. Under the B/D proxy, west Bohemia leads by loan count (9/57) and north Moravia by principal when grouped by booking branch. The portfolio has 682 distinct owners of borrowing accounts. The 1997 mean is 30,731,364 / 196 = 156,792.67 source units. |
| [Structured challenge](evidence/structured_challenge.json) | Of 30 frozen case cards, 14 expected numerical answers and 16 expected holds passed their technical checks. Six additional T7/T8 calculations are reported separately. |
| [Shadow readiness](evidence/shadow_readiness.json) | The independent intake and reviewer ledgers are empty. The scorer requires preserved original candidates and actual review times. |

The validation decision is to withhold automatic release for analyst triage. A supervised trial would require an independently scored human holdout, access testing in the target environment and a decision from the responsible owners. Wretblad et al. published two illustrated predictions for Q177. A complete set for Figure 2 was unavailable in the pinned release. The report identifies their Figure 2 values as published.

## Build the PDF

Run the following from the repository root with pdfLaTeX, latexmk, STIX2, Fira Sans/Mono and the TikZ/tcolorbox packages installed. The rebuilt PDF is written to `.build/report/main.pdf`.

    latexmk -cd -pdf -halt-on-error -interaction=nonstopmode -outdir=../.build/report report/main.tex

The original pilot logs, questions and database are identified by their checksums. The source documents named in the final audit have a separate checksum list. [Course assignment and proposal](archive/course_sources/) · [Source checksums](archive/course_sources/SHA256SUMS)

This release includes the inputs used in Appendix E. The paper authors’ inputs are pinned to `6930cf6f9abaf50a3407f96b9facbda11835eec2`. [Pilot input manifest](archive/manifest.json) · [Financial evaluation questions](archive/text2sql_bird/bird_financial_dev.json)
