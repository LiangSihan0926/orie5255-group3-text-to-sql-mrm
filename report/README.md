# Report source and replication supplement

This directory accompanies Group 3’s ORIE 5255 report on a Text-to-SQL agent for bank portfolio analytics. The replication uses the financial subset of BIRD to check two published annotation tables and determine how corrections to the reference SQL change the answers used to score a model. [Wretblad et al., arXiv:2402.12243v4](https://arxiv.org/abs/2402.12243v4)

## Run the ten checks

From the repository root, run the following command with Python 3.10 or later and its standard SQLite module.

```sh
python3 -B report/verify_supplement.py
```

From inside this directory, use `python3 -B verify_supplement.py`. Both commands work offline. The runner unpacks the repository’s `data/financial.sqlite.gz` in a temporary directory. The release comparison verifies the uncompressed database SHA-256 (`d15d89cdb068a202b6f2b99342af44dffc1d52545b39ceaf62efdc0ba570101e`) before executing the published reference queries in read-only mode. It writes comparison flags in the temporary directory and checks the resulting CSV byte for byte. The other scripts compare results with the archived CSV or JSON for the corresponding test. A difference stops the run with a nonzero exit status.

| Check | Evidence | What to verify |
| --- | --- | --- |
| Financial annotations | [financial_label_recount.json](evidence/financial_label_recount.json) | Of 106 items, 52 have at least one noise label. The released annotations contain 24 spelling/syntax labels. The paper prints 23. |
| Reference SQL releases | [gold_release_comparison.csv](evidence/gold_release_comparison.csv) | For each of 106 IDs, four pairwise comparisons check question text, SQL text and complete result rows with duplicate multiplicities. Relative to the authors’ original, the SQL-only, fully corrected and team releases change 24, 23 and 32 outputs. Of the 24 SQL-only changes, 18 have an original SQL-error label and six have only question labels. |
| Archived pilot | [archive_diagnostics.json](evidence/archive_diagnostics.json) | Checks 227 saved numeric answers at the precision shown, along with indicator formulas, maturity dates and the currency labels in the archive. |
| Pilot disclosure rules | [pilot_disclosure_audit.csv](evidence/pilot_disclosure_audit.csv) | Counts caveat keyword failures among the 46 applicable matches, single-value outputs and supporting cohort counts for each T8 interpretation. |
| English resubmissions | [clarification_paths.csv](evidence/clarification_paths.csv) | After six known clarification prompts, ten of 11 complete requests agree with the base records. Actual repayment status at year-end 1996 remains unavailable. |
| Clarified portfolio queries | [clarified_portfolio_queries.csv](../evidence/clarified_portfolio_queries.csv) | Checks the eight regional ranks under each of 12 definitions, the distinct-owner count, six individual years and the six rows of the year-by-year result. These 20 queries produce 109 evidence rows. |
| Illustrated Q177 predictions | [published_q177_replay.json](evidence/published_q177_replay.json) | Replays both DIN-SQL predictions printed in Figure 8 as shown and with one missing comma inserted in each. Only the edited prediction for the reworded question matches the reference. |
| T4 withdrawal timing | [withdrawal_timing.json](evidence/withdrawal_timing.json) | Groups loans by whether the account’s first recorded card withdrawal preceded, coincided with or followed loan approval. Reconciles the four mutually exclusive cohorts, including loans with no observed event. |
| T4 query logic | [t4_schema_stress.json](evidence/t4_schema_stress.json) | Seven synthetic scenarios on the original table definitions cover repeated transactions, multiple loans and empty evidence under different coverage assumptions. |
| Snapshot and cache binding | [snapshot_binding.json](evidence/snapshot_binding.json) | Three compatible combinations pass and four mismatches are held, including a stale result with the expected numeric value. |

The release comparison measures how the benchmark key changes. The two Q177 predictions printed in Figure 8 support a separate one-item check. Rescoring Figure 2 as originally evaluated would require predictions for every item and condition. New model calls would be a new experiment. [Authors’ release](https://github.com/niklaswretblad/the-effects-of-noise-in-text-to-SQL/tree/6930cf6f9abaf50a3407f96b9facbda11835eec2)

The [project evidence directory](../evidence/) contains the pilot scorecards, reference calculations and controller tests. Each result is stored once. For the project validation commands and archive provenance, see the [repository README](../README.md) and [source manifest](../archive/manifest.json).

## Compile the report

From the directory containing `main.tex`, use a TeX installation with pdfLaTeX, latexmk, STIX2, Fira Sans/Mono, TikZ and tcolorbox. The rebuilt PDF is written to `../.build/report/main.pdf`.

```sh
latexmk -pdf -halt-on-error -interaction=nonstopmode -outdir=../.build/report main.tex
```

The Rho document class by Guillermo Jimenez is distributed under CC BY 4.0. The source retains the class attribution and documentation. [Rho documentation](rho-class/README.md)

The four paper-author text inputs retain their published bytes. Their provenance, attribution, and the upstream BIRD dataset terms are recorded with the files. [Paper-author input notice](inputs/wretblad/NOTICE.md) · [BIRD data notice](../data/NOTICE.md)
