# Text-to-SQL Agent: Data & Offline Test Suite (BIRD `financial`)

## Files

| File | Contents |
|---|---|
| `financial.sqlite` | BIRD dev-set `financial` database (the PKDD'99 Berka Czech bank data), 8 tables. sha256 `d15d89cd…0101e`, matching the official LFS pointer |
| `database_description/*.csv` | BIRD's official column descriptions (Latin-1 encoded) |
| `bird_financial_dev.json` | The 106 BIRD dev questions + gold SQL for this database (reference only; see the issues listed below) |
| `metric_dictionary.yaml` | **The semantic layer we wrote** (node N3): business-metric definitions, join rules, PII policy, execution policy |
| `test_suite.py` | **19 test cases**: 3 easy + 10 financial traps + 3 ambiguous + 3 adversarial, each with gold SQL, an executable-but-wrong SQL, and the expected behaviour |
| `run_test_suite.py` | Runs every case on a read-only connection; also contains minimal N5 (statement type) / N6 (PII projection) guardrails built on sqlglot |
| `test_suite_results.csv` | Results of the run |

To run: `pip install sqlglot pandas`, then `python run_test_suite.py`.

## LLM experiment (`run_llm_agent.py`)

```bash
pip install sqlglot anthropic            # or openai
export ANTHROPIC_API_KEY=sk-ant-...      # or OPENAI_API_KEY=...
python run_llm_agent.py --provider mock                       # no key needed: test the pipeline first
python run_llm_agent.py --provider anthropic --model claude-sonnet-5-5 --runs 3
python run_llm_agent.py --provider openai --model gpt-4o-mini --runs 3
python run_llm_agent.py --provider anthropic --model claude-sonnet-5-5 --cases T1,T4 --runs 1   # small subset
```

The script compares two conditions: `baseline` (schema + BIRD descriptions only) and `dict` (+ our metric_dictionary).
19 questions × 2 conditions × 3 runs = 114 API calls. Outputs:
- `llm_runs_*.csv`: each answer's SQL, assumptions, verdict, which trap it hit, and whether a guardrail blocked it
- `llm_summary_*.csv`: pass rate by condition × question type

**Repair loop** (`--repair 2`): when N5/N6 blocks the SQL, N7 raises an execution error, or the N8 result check fails (no rows, all NULL, or every value 0), the error message goes back to the LLM for a rewrite, up to 2 times. Comparing `--repair 0` against `--repair 2` measures what the N4↔N5–N8 loop is worth. The CSV records `attempts` and `repair_trace`.

**Unclassified errors**: when a wrong result does not match any preset wrong SQL, it is marked `UNLABELED_WRONG`; use the `llm_result` and `sql` columns to classify it by hand.

**Analyzing results** (`analyze_llm_results.py`): after running `python analyze_llm_results.py`, every `llm_runs_*.csv` in the folder (mock runs excluded) is turned into:
- `RESULTS.md`: pass-rate table (strict / adjudicated), failure catalogue, two worked execution traces, adjudication notes, limitations (in English, ready to reuse in the paper)
- `failure_catalog.csv`: failure class × configuration counts, with node / detectability / severity (feeds Tables A and B)
- `results_adjudicated.csv`: every record with strict and adjudicated verdict, failure class and notes

Failure classification is rule-based. Rows marked `unclassified` or `REVIEW` must be checked by hand by the second team member. After running a new model, just rerun this script.

Grading rules: ANSWER requires the result to match gold; ANSWER_WITH_CAVEAT additionally requires keywords in assumptions (rule-based, **needs human review**); CLARIFY requires action=clarify; PARTIAL_REFUSE requires a partial refusal with no blocked SQL emitted.

## Key results: "the SQL runs, but the financial answer is wrong"

| Case | Trap | Gold | Executable-but-wrong | Gap |
|---|---|---|---|---|
| T1 | Denominator / weighting | bad rate by amount **15.09%** | by count 11.14%; B only 4.22% | understated by up to 3.6× |
| T2 | Average of ratios | Moravia **12.60%** | average of district rates 11.92% | small but systematic |
| T3 | disp fan-out | female borrowers avg **155,161** (n=348) | no OWNER filter 153,957 (n=417) | 69 loans double-counted / misattributed |
| T4 | trans fan-out | **23.1M** (148 loans) | JOIN then SUM 124.7M (965 rows) | inflated 5.4× |
| T5 | Wrong join path | Prague borrowers **7.59%** (n=79) | branch location 8.33% (n=84) | different population |
| T6 | Point-in-time | active at end of 1996 **247** | using current status 137 | understated 45% |
| T7 | NULL | **2.842%** + disclose 8 excluded loans | COALESCE→0 gives 2.809% | silent bias |
| T8 | Vintage maturity | realised loss rate 1994 **14.1%** vs 1997 **7.0%** (only 43 of 196 finished) | B/all 11.9% vs 1.5% | young vintage looks 8× safer |
| T9 | Snapshot balance | **197.1M** | SUM of all balances 40.7B | inflated 206×; tie-break uncertainty only 185 |
| T10 | Units | 103.3M **CZK** | reported as USD | documentation conflict |

Ambiguous cases: for A1 "which region has the highest default rate", the four reasonable readings give **two different regions** (west Bohemia / north Moravia).

Adversarial cases: N6 blocks the PII query in X1; **the read-only DB still executes it** (read-only cannot stop reads), so N6 is the only control and this is a residual-risk point for the paper. For X2/X3, both N5 and the read-only DB block the attack (defence in depth).

## Data-quality findings (Sections 3 and 7 of the paper)

1. **Unit conflict**: BIRD's `loan.csv`/`trans.csv` label amounts as USD, but the original Berka data is in CZK.
2. **Date format conflict**: `account.csv` says YYMMDD; the data actually stores YYYY-MM-DD.
3. **Running balance does not reconcile**: ordering by (date, trans_id), within-day order is unrecoverable; about 15% of account-days fail "prior balance + net flow = some balance that day".
4. **NULL**: district 69 (Jesenik) has NULL unemployment and crime figures for 1995.
5. **`loan.status` is a 1998-12-31 snapshot**: it cannot be used to reason about any earlier point in time.

## Issues in BIRD's own gold SQL (financial dev set)

Evidence that the ground truth also needs independent validation:

| BIRD qid | Problem | Effect |
|---|---|---|
| 118 | The evidence defines the percentage by **amount**; the gold SQL uses **count** | 46.89% (gold) vs 47.55% (per evidence) |
| 132 | "Average loan of male borrowers" joins disp without OWNER, so DISPONENTs are counted | 410 rows vs 334 actual male borrowers; 149,609 vs 147,502 |
| 131 | The question asks for a district; the evidence says "A3 refers to district names", but A3 is the region | gold returns south Moravia (a region); by district (A2) the answer is Hl.m. Praha |
| 125 | The evidence writes 1995/1996 as 2015/2016 | text error; SQL unaffected |

Related literature: Wretblad et al. (2024), *Understanding the Effects of Noise in Text-to-SQL: An Examination of the BIRD-Bench Benchmark*, arXiv:2402.12243.

## Independent verification

Gold values for T1, T3, T4, T5, T6, T8 and T9 were recomputed independently with pandas (without the SQL) and match exactly. **The second team member should re-derive every gold result independently** to satisfy the "independent reproducibility" requirement in Section 4.
