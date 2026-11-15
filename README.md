# Validating a Text-to-SQL Agent for Bank Portfolio Analytics

ORIE 5255 Capstone · Topic 2 · Group 3

Sihan Liang (sl3639) and Minxi Lin (ml2934)

An independent validation study for a single-turn, read-only assistant to an
internal portfolio-risk analyst. The study uses the BIRD `financial` SQLite
snapshot, 19 team-authored questions, and 456 archived run records. Its focus is
how executable SQL can misstate a financial metric and how a validator should
detect, contain, and monitor that risk.

## Deliverables

- [Final English paper in PDF](deliverables/Group_3_Topic_2_Final_Report.pdf)
  and [editable Word version](deliverables/Group_3_Topic_2_Final_Report.docx)
- [12-minute presentation with speaker notes](deliverables/Group_3_Topic_2_Presentation.pptx)
- [Node traceability matrices](docs/traceability.md) and
  [evaluation and review protocol](docs/evaluation_protocol.md)
- [Course requirements and evidence map](docs/course_mapping.md)
- [Original proposals, assignment and experiment files](archive/manifest.json)

## Reproduce the validation

Use Python 3.10+ with SQLite support. The offline validation needs only the
standard library and the files in this repository.

```sh
python3 -B -m validation.run
python3 -B -m unittest discover -s tests -v
```

The runner verifies the archived files and raw snapshot hash, reconstructs the
pilot scorecard, recalculates references from base tables in Python, and checks
T4 with a gate replay and four synthetic fixtures. It writes aggregate JSON and
CSV to [evidence/](evidence/). An existing raw SQLite copy can be supplied with
`--db` if its bytes match the manifest. Use `--output` for a separate run folder.

The pilot scripts are preserved for provenance. The offline runner opens the
frozen snapshot read-only, fingerprints archived candidate SQL as text, and
executes only predefined fixture queries on synthetic data. Model APIs and
live database credentials are unnecessary.

## Results and decision

- Independent calculations reproduced the archived numerical references or
  candidate interpretations for all 19 cases under explicit definitions.
  The interpretations for T7 and T8 still require business adjudication.
- Among 312 routine/trap records, 227 had an answer action and a final
  result without a logged guardrail, execution error, or result flag. Of
  those 227, 84 differed on the archive's key-result check.
- Trap questions account for 81 of the 84 mismatches (81/164 runtime-clean
  trap answers). Twelve pooled mismatches are open T7 weighting disputes.
  Separately, 17 key-result matches failed the archived caveat check.
- For T4, 12 of 24 archived records returned the independently verified
  amount, eight returned larger amounts, and four lacked a runtime-clean
  answer. The smallest of the eight overstatements was 570.3%.
- For T4, a narrow two-template gate retained all six matching candidates
  and intercepted five mismatches among the 11 runtime-clean candidates.
  It also deferred two valid SQL forms in a separate constructed test.
- The original system is rejected for automatic release of portfolio
  aggregates. A supervised shadow trial on independently approved templates
  is a possible later decision after the remediation and review gates in the
  paper have been met.

The 456 observations repeat 19 questions on one historical snapshot. The
benchmark spot checks, archive replay and synthetic fixtures answer different
questions. No new LLM calls, independent human sign-off, or production outcome
measurement were performed in this package.

The [configuration funnel](evidence/numeric_by_configuration.csv),
[policy breakdown](evidence/repair_policy_by_case.csv) and
[T4 amount audit](evidence/t4_amount_audit.csv) expose the denominators and
enable independent review without rerunning archived SQL.

[Data provenance and licensing](data/NOTICE.md)
