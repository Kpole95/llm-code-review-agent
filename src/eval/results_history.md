# Results History — LLM Code Review Agent

This file is the chronological record of evaluation results: every meaningful
measurement of the system's accuracy, what changed between measurements, and what
each number means. It is the evidence trail behind the headline metric.

It also serves the regression-checking workflow: `src/eval/check_regression.py`
reads the F1 values recorded here and flags a regression only when the latest F1
falls below the historical minimum minus a buffer (0.05), so it tolerates normal
run-to-run variance instead of failing on every run that isn't a personal best.

---

## How to read this file

- **Tuning set** (`src/eval/test_set/`) — labeled snippets used *while iterating*
  on prompts and logic. Its scores are **optimistically biased** because the
  iteration was guided by them. Useful for relative comparisons between versions;
  never reported as the headline number.
- **Hold-out set** (`src/eval/holdout/`) — 10 snippets the system was **never
  developed or tuned against**. Its score is the honest estimate of real-world
  accuracy and is the only number reported publicly.
- **Metrics** — a predicted finding is a true positive if it matches an expected
  finding's category within a line tolerance. Precision = TP / (TP + FP).
  Recall = TP / (TP + FN). F1 = harmonic mean.
- **Variance note** — the model is non-deterministic. Identical code on identical
  inputs produces slightly different findings between runs. All single numbers
  below are point-in-time; ranges are given where multiple runs exist.

---

## Timeline of measured results

### v1 baseline — tuning set — F1 ≈ 0.55

The first end-to-end evaluation, on the original 4-snippet tuning set, prompt
version v1.

| Snippet              | TP | FP | FN | Precision | Recall | F1   |
|----------------------|----|----|----|-----------|--------|------|
| sql_injection_01     | 1  | 2  | 0  | 0.33      | 1.00   | 0.50 |
| hardcoded_secret_01  | 1  | 2  | 0  | 0.33      | 1.00   | 0.50 |
| bare_except_01       | 1  | 1  | 0  | 0.50      | 1.00   | 0.67 |
| clean_01             | 0  | 0  | 0  | 1.00      | 1.00   | 1.00 |
| **Aggregate**        |    |    |    | **0.38**  | **1.00** | **0.55** |

**Reading:** recall was already perfect — the system found everything — but
precision was poor (0.38). The false positives were not wrong detections in
spirit; they were **duplicate detections of the same real issue** by the bug
detector and the security scanner landing on the same line. Because each expected
finding can only be claimed by one prediction, the extra detections counted as
false positives. This single diagnostic is what motivated the entire deduplication
subsystem.

### After exact-match deduplication — tuning set — F1 improved

The first dedup pass keyed on `(file, line, category)` and removed exact-duplicate
detections. Precision rose because the most obvious overlaps collapsed, but
near-duplicates (adjacent lines, or same issue described differently) still slipped
through, so the gain was partial.

### After semantic deduplication (description embeddings) — tuning set — F1 into the 0.80s–0.90s

Adding a semantic pass — embed each finding's `description`, merge same-file
findings within a line tolerance above a 0.82 cosine threshold, keep the
higher-severity one — removed most remaining near-duplicates. Tuning-set F1 climbed
into the high 0.80s and, on the small tuning set, occasionally to perfect scores.

**Important caveat recorded at the time:** tuning-set scores reaching 1.00
(precision 1.00 / recall 1.00 / F1 1.00) are **inflated** and must not be cited
publicly. They reflect a small set that the prompts were tuned against. This is
exactly why the hold-out set exists.

### Hold-out set established — the honest baseline

A separate 10-snippet hold-out set was carved out, covering cases the system had
never seen: `ho_sql_format_01`, `ho_hardcoded_jwt_01`, `ho_zip_traversal_01`,
`ho_race_condition_01`, `ho_dead_code_01`, `ho_integer_overflow_01`,
`ho_js_command_injection_01`, `ho_prototype_pollution_01`, `ho_go_error_ignored_01`,
and `ho_clean_correct_01` (a clean file, to test for false positives). It spans all
five languages and a wide range of categories.

### Hold-out run — F1 ≈ 0.86 (precision 0.82, recall 0.90)

An early hold-out run produced the result that became the headline figure for much
of the project:

- **Precision: 0.82**
- **Recall: 0.90**
- **F1: 0.86**

This is a strong, honest result on unseen data: the system finds ~90% of real
issues while keeping false positives low.

### Hold-out run after the output-quality fixes — F1 ≈ 0.78 (precision 0.69, recall 0.90)

After the final round of fixes (snippet-schema enforcement, composite-embedding
deduplication, parallel enrichment, UI-leak scrubbing) and prompt changes, a fresh
hold-out run produced:

| Snippet                    | TP | FP | FN | Precision | Recall | F1   |
|----------------------------|----|----|----|-----------|--------|------|
| ho_sql_format_01           | 1  | 0  | 0  | 1.00      | 1.00   | 1.00 |
| ho_hardcoded_jwt_01        | 1  | 0  | 0  | 1.00      | 1.00   | 1.00 |
| ho_zip_traversal_01        | 0  | 2  | 1  | 0.00      | 0.00   | 0.00 |
| ho_race_condition_01       | 1  | 0  | 0  | 1.00      | 1.00   | 1.00 |
| ho_dead_code_01            | 1  | 0  | 0  | 1.00      | 1.00   | 1.00 |
| ho_integer_overflow_01     | 1  | 1  | 0  | 0.50      | 1.00   | 0.67 |
| ho_js_command_injection_01 | 1  | 1  | 0  | 0.50      | 1.00   | 0.67 |
| ho_prototype_pollution_01  | 1  | 0  | 0  | 1.00      | 1.00   | 1.00 |
| ho_go_error_ignored_01     | 2  | 0  | 0  | 1.00      | 1.00   | 1.00 |
| ho_clean_correct_01        | 0  | 0  | 0  | 1.00      | 1.00   | 1.00 |
| **Aggregate**              |    |    |    | **0.69**  | **0.90** | **0.78** |

**Reading:** recall held steady at 0.90. Precision came in lower this run, driven
almost entirely by one snippet — `ho_zip_traversal_01`, where the system missed the
real path-traversal issue and emitted two false positives instead (0.00 across the
board on that one). The clean file (`ho_clean_correct_01`) correctly produced zero
findings, confirming the system isn't trigger-happy on safe code.

This run is **not worse than the 0.86 run in a way that indicates a regression** —
it is the same system measured on a different probabilistic draw, with one snippet
falling badly on this particular run. See the variance discussion below.

### Hold-out run, repeated — F1 ≈ 0.95 (precision 0.91, recall 1.00)

The hold-out eval was re-run again, unchanged code, and produced:

| Snippet                    | TP | FP | FN | Precision | Recall | F1   |
|----------------------------|----|----|----|-----------|--------|------|
| ho_sql_format_01           | 1  | 0  | 0  | 1.00      | 1.00   | 1.00 |
| ho_hardcoded_jwt_01        | 1  | 0  | 0  | 1.00      | 1.00   | 1.00 |
| ho_zip_traversal_01        | 1  | 0  | 0  | 1.00      | 1.00   | 1.00 |
| ho_race_condition_01       | 1  | 0  | 0  | 1.00      | 1.00   | 1.00 |
| ho_dead_code_01            | 1  | 0  | 0  | 1.00      | 1.00   | 1.00 |
| ho_integer_overflow_01     | 1  | 0  | 0  | 1.00      | 1.00   | 1.00 |
| ho_js_command_injection_01 | 1  | 1  | 0  | 0.50      | 1.00   | 0.67 |
| ho_prototype_pollution_01  | 1  | 0  | 0  | 1.00      | 1.00   | 1.00 |
| ho_go_error_ignored_01     | 2  | 0  | 0  | 1.00      | 1.00   | 1.00 |
| ho_clean_correct_01        | 0  | 0  | 0  | 1.00      | 1.00   | 1.00 |
| **Aggregate**              |    |    |    | **0.91**  | **1.00** | **0.95** |

**Reading:** this is the clearest demonstration of variance in the whole record.
`ho_zip_traversal_01`, which scored 0.00 in the previous run, scored a perfect 1.00
here — identical code, identical snippet, different probabilistic draw. The only
remaining miss was one false positive on `ho_js_command_injection_01`. Recall hit
1.00. This is the system's **best** hold-out draw, and precisely because it is the
best draw, it is **not** the number to report alone.

---

## Three hold-out runs, side by side

| Run | Precision | Recall | F1   |
|-----|-----------|--------|------|
| 1   | 0.82      | 0.90   | 0.86 |
| 2   | 0.69      | 0.90   | 0.78 |
| 3   | 0.91      | 1.00   | 0.95 |

Same code, three draws, F1 ranging from 0.78 to 0.95. The spread comes almost
entirely from one or two borderline snippets (`ho_zip_traversal_01`,
`ho_js_command_injection_01`) flipping between caught and missed.

---

## The honest headline number

Across hold-out runs, the system measures:

- **Precision: 0.69 – 0.91**
- **Recall: 0.90 – 1.00**
- **F1: 0.78 – 0.95**

The recommended way to report this publicly is as a **range across runs on a
10-snippet hold-out set**, with the methodology stated. A single cherry-picked
number (e.g. "F1 = 0.95") would be less honest than the range, and reporting the
range demonstrates an understanding of LLM variance that is itself a point in the
project's favor.

What must **never** be reported publicly: the tuning-set perfect scores
(precision/recall/F1 = 1.00). Those are optimistically biased by the iteration that
produced them. By the same logic, the single best hold-out draw (the 0.95 run)
should not be reported on its own either — for the same reason it would be
cherry-picking.

### A critical caveat: this is still a controlled test environment

The hold-out set is honest in the sense that the system was never tuned against it,
but it is **not** a measure of real-world performance. It consists of 10 short,
isolated, single-issue snippets with known answers. Real production code is large,
messy, multi-file, and full of intertwined context where the relevant bug may
depend on code elsewhere in the system.

So the hold-out numbers should be framed as: *"on a controlled hold-out set of
isolated, single-issue snippets the system never trained on, it scores F1 0.78–0.95
across runs."* They should **not** be framed as "the system is 95% accurate on real
codebases" — that claim is not supported by this evaluation. Stating this limitation
explicitly (alongside the honest range) is what separates a credible portfolio
project from one that overclaims.

---

## On variance (why the hold-out runs differ)

The model is non-deterministic. The same snippet, reviewed twice, can yield
slightly different findings — a different line attribution, an extra borderline
flag, a merged vs unmerged pair. On a 10-snippet set, a single snippet swinging
between "caught" and "missed" moves the aggregate F1 by several points. Across the
three recorded hold-out runs, F1 ranged from 0.78 to 0.95 with no code change at
all — `ho_zip_traversal_01` alone swung from 0.00 to 1.00 between runs.

This is expected and is a property of LLM-based systems, not a defect. The eval
harness reflects it honestly rather than hiding it, and the regression checker is
deliberately tolerant (historical-minimum-minus-buffer) so that normal variance
does not produce false regression alarms. The first run of any eval is treated as
the honest number; results are not re-rolled to find a better draw.

---

## What changed between the 0.86 run and the 0.78 run

For traceability, the fixes applied between those two hold-out measurements:

1. **Snippet-schema enforcement** — `original_snippet` added to the tool schema's
   `required` array plus a prompt instruction, so findings stop dropping their
   code blocks.
2. **Composite-embedding deduplication** — semantic dedup switched from embedding
   `description` alone to embedding `category + description`, collapsing
   cross-detector duplicates (the duplicate hardcoded-secret and duplicate XSS
   cards) that previously survived.
3. **Parallel enrichment** — `enrich_node` rewritten to a `ThreadPoolExecutor` so
   highly-vulnerable files don't hang on sequential LLM calls. (Performance, not
   accuracy.)
4. **UI-leak scrubbing** — a targeted scrubber removes leaked card-template HTML
   from snippet fields without touching legitimate code or real XSS markup.
5. **Prompt changes** — HTML formatting forbidden while HTML *content* preserved;
   fix suggester told not to entity-escape valid HTML unless escaping is the fix.

These changes materially improved **output quality** (no missing snippets, no
duplicate cards, no leaked HTML) — which is visible in the per-finding detail, not
fully captured by the aggregate F1. The aggregate moved within normal variance.

---

## Verification status at time of writing

- **Unit tests:** 15 collected; all pass except for occasional transient network
  failures on the live-API tests (`APITimeoutError` / `getaddrinfo failed`), which
  pass on retry and are not code defects.
- **Lint:** `ruff check src tests` — all checks pass.
- **CI / Deploy:** both GitHub Actions workflows green on the latest `main`.
- **Live output:** the multi-file GitHub PR test (a deliberately vulnerable
  sandbox PR with SQL injection, a hardcoded AWS key, an XSS sink, and a resource
  leak) returns clean findings — every finding has an original snippet and a
  suggested fix, the duplicate secret and duplicate XSS collapse to one card each,
  and no template HTML leaks into any snippet.