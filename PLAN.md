# data_reconcile

## 1. Project Objective

`data_reconcile` is a Python system for reconciling two independent Qualtrics data-entry datasets created from the same paper surveys.

```text
Dataset A ──┐
            ├──► Validation ──► Matching ──► Comparison ──► Review ──► Final Dataset
Dataset B ──┘
```

**Scope:** the work focuses on the fields where the two entries of the same paper survey **disagree**. Fields where both entries agree (exactly, or after safe normalization) are accepted as entered and need no human attention. Every field is still compared, because that is how the disagreements are found, but only disagreements reach the reviewer.

In this project:

* **Dataset A** = entries by Himal (survey code ends in `HS`)
* **Dataset B** = entries by the coworker (survey code ends in `CH`)
* Both were entered into the same Qualtrics survey ("ERC Flood Survey"), so A and B come from **one export**, split by the initials at the end of the survey code (`QID2`).

The system will:

* Check that both datasets can be loaded and structurally compared
* Compare their structures
* Match corresponding records
* Determine which fields require comparison
* Normalize safe formatting differences
* Compare every relevant field
* Handle different Qualtrics question types
* Classify discrepancies
* Automatically resolve only safe differences
* Send substantive/ambiguous differences to human review
* Record every decision and correction
* Generate a validated final dataset
* Maintain a complete audit trail

---

# 2. Data Management

Raw Qualtrics exports remain read-only (file permissions are set to read-only).

```text
data/
├── raw/                                           ← read-only originals
│   ├── erc_flood_qualtrics_export_2026-09-28.csv  ← one export: HS + CH (+ entries with no initials)
│   ├── erc_flood_survey_definition.qsf            ← survey structure (questions, choices, Other fields)
│   └── hs_paper_log.txt                           ← Himal's paper log of survey numbers entered
├── working/                                       ← generated from raw/, safe to delete and rebuild
│   ├── hs_unique_surveys.csv
│   ├── hs_set_aside.csv
│   ├── hs_duplicate_codes.csv
│   └── hs_paper_log_not_in_qualtrics.csv
├── review/                                        ← human decisions (kept across runs)
└── final/
```

The Qualtrics export is **numeric values** with **multi-value fields split into columns** (one 0/1 column per check-all option).

All processing occurs on derived data. The original files are never overwritten. `data/` is excluded from Git; participant data is never committed.

### Current working set

For now, only Himal's entries that are unambiguous are used:

* An `HS` entry is kept only if its survey number appears **exactly once** among the `HS` entries in Qualtrics **and exactly once** in the paper log → **416 surveys** (`hs_unique_surveys.csv`).
* The other 138 `HS` entries are set aside, with the reason, in `hs_set_aside.csv` (repeated codes, codes missing from the paper log, a code repeated on the paper log). The team will decide how to handle them; the decisions will then bring them back in.
* Entries with no initials (175) are ignored.
* `scripts/select_working_set.py` rebuilds `data/working/` from `data/raw/`.

The coworker's (`CH`) entries are not available yet. Until they are, the system is built and tested with synthetic `CH` data.

---

# 3. Dataset Validation

Validation is limited to what the comparison needs in order to be reliable. Each dataset is checked for:

* File integrity and encoding (raw files are fingerprinted with SHA-256)
* The three Qualtrics header rows (variable name, question text, ImportId)
* Record and column counts
* Duplicate columns
* Missing/extra fields
* Response identifiers (survey code present and in the expected format, e.g. `1-0836 HS`)
* Question/variable identifiers

Rule checks on individual answers (e.g. Other selected without text, more than one box ticked on a one-answer question) are **optional and off by default**, because values that both entries agree on are accepted as entered. They can be switched on in `config/validation_rules.json`.

Validation results are stored separately from reconciliation results.

---

# 4. Structure and Field Mapping

Before response comparison, Dataset A and Dataset B are structurally compared.

The process checks:

* Column names
* Column order
* Missing columns
* Extra columns
* Duplicate columns
* Question/variable identifiers
* Metadata fields

Each field is classified as:

```text
COMPARE
EXCLUDE
IDENTIFIER
METADATA
VALIDATION_ONLY
SPECIAL_COMPARISON
```

Survey-specific rules are stored in configuration files rather than hard-coded.

```text
config/
├── questions.json
├── normalization_rules.json
└── validation_rules.json
```

`questions.json` is **generated from the `.qsf` file** and then reviewed once by a person. It records, for each of the 31 questions: its type (single choice, check-all, matrix/grid, open text), the choices, the physical columns, and the 17 Other + text pairs.

Columns are matched to questions using the **ImportId** (third header row), not the column name. In this survey the names don't always match the internal IDs (e.g. column `Q11_7` is matrix row 8, "Property damage").

Qualtrics metadata columns (`StartDate`, `EndDate`, `RecordedDate`, `Duration`, `ResponseId`, `IPAddress`, location, etc.) are expected to differ between the two entries and are classified `METADATA` (not compared).

---

# 5. Record Matching

Records are matched using configured identifiers such as:

* Paper survey ID
* Participant ID
* Survey number
* Embedded data
* Other unique identifiers
* Valid combinations of fields

In this project the identifier is the **survey code** in `QID2` with the entrant's initials removed: `1-0836 HS` and `1-0836 CH` → `1-0836`. Only safe clean-up is applied to the code (trim spaces, remove initials, upper-case). A code that looks mistyped (e.g. `10619` instead of `1-0619`) is suggested for review, never corrected automatically.

Matching happens in two steps:

1. **Within each entrant:** every survey code must appear once. Repeated codes (e.g. the 63 repeated `HS` codes) are set aside until a person decides whether they are two different surveys or a duplicate entry.
2. **Between A and B:** codes that appear once in each dataset are paired.

Row position is not treated as a reliable identifier.

The matching process identifies:

```text
MATCHED
UNMATCHED_A
UNMATCHED_B
DUPLICATE
AMBIGUOUS
```

Unmatched or ambiguous records are not automatically paired.

---

# 6. Normalization

A controlled normalization layer handles differences that do not change the recorded response.

Possible operations include:

* Leading/trailing whitespace
* Repeated whitespace
* Line endings
* Unicode normalization
* Capitalization where appropriate
* Harmless formatting differences

Both original and normalized values are retained.

Normalization never decides that two substantively different responses are equivalent.

---

# 7. Field Comparison

Every configured field for every matched record is compared.

Each comparison records:

```text
survey_id
field
question_id
question_type
dataset_a_original
dataset_b_original
dataset_a_normalized
dataset_b_normalized
status
difference_type
reason
review_required
```

Comparison states include:

```text
EXACT_MATCH
MATCH_AFTER_NORMALIZATION
FORMAT_ONLY_DIFFERENCE
POTENTIAL_TEXT_MATCH
VALUE_MISMATCH
MISSING_VS_PRESENT
INVALID_VALUE
UNEXPECTED_VALUE
UNMATCHED_RECORD
DUPLICATE_RECORD
REQUIRES_MANUAL_REVIEW
UNKNOWN
```

---

# 8. Question-Type-Aware Comparison

Comparison logic depends on the Qualtrics question type.

### Single Choice

Compare selected values directly.

### Multiple Choice

Compare selections as sets when ordering is irrelevant.

### Matrix/Grid

Compare individual rows or components so the exact discrepancy is identified.

### Open-Ended

Use text normalization and optional similarity analysis.

### Other Responses

Treat the Other-selection field and its associated description as related fields.

### Missing Values

Distinguish matching blanks from missing-vs-present discrepancies.

---

# 9. Text Comparison

Open-ended fields receive additional processing for:

* Whitespace
* Capitalization
* Punctuation
* Unicode
* Line breaks
* Formatting
* Potentially equivalent wording

Text similarity may identify potentially equivalent responses, but similarity does not automatically change either response.

Potential text matches remain available for human review.

---

# 10. Discrepancy Handling

The system separates detection from correction.

```text
Difference
    ↓
Classification
    ↓
Safe normalization OR
Human review
    ↓
Final value
```

Safe formatting differences may be resolved automatically.

Substantive differences such as conflicting answers, uncertain names, ambiguous text, or unclear handwriting remain unresolved until reviewed.

The system never chooses a value simply because it appears more reasonable.

---

# 11. Human Review

The review queue contains **only the disagreements**. Fields where both entries agree never appear in it.

A structured review queue contains:

```text
survey_id
field
question_id
question_type
dataset_a_value
dataset_b_value
normalized_values
difference_type
reason
review_status
final_value
reviewer
review_date
review_notes
```

Possible decisions include:

```text
DATASET_A_CORRECT
DATASET_B_CORRECT
BOTH_INCORRECT
ORIGINAL_PAPER_REQUIRED
AMBIGUOUS
UNABLE_TO_DETERMINE
```

When necessary, the original paper survey becomes the authoritative source.

---

# 12. Final Value and Provenance

Every resolved field receives a final value and a source:

```text
BOTH_ENTRIES_AGREE
DATASET_A
DATASET_B
SAFE_NORMALIZATION
HUMAN_REVIEW
ORIGINAL_PAPER_SURVEY
```

Fields where both entries agree take the agreed value (`BOTH_ENTRIES_AGREE`) without review.

The final dataset is generated only after required discrepancies have been resolved.

```text
data/final/final_dataset.csv
```

---

# 13. Audit Trail

Every meaningful transformation and decision is recorded.

```text
audit_log.csv
```

The audit trail contains:

```text
survey_id
field
original_a_value
original_b_value
normalized_a_value
normalized_b_value
final_value
action
decision_source
reason
reviewer
timestamp
```

This provides traceability from the final value back to the original entries and the evidence used to resolve them.

---

# 14. Reports and Outputs

The system produces:

```text
output/
├── comparison_results.csv
├── review_queue.xlsx
├── audit_log.csv
├── final_dataset.csv
├── summary_report.html
└── validation_report.txt
```

The summary report includes:

* Dataset sizes
* Matched/unmatched records
* Fields compared
* Exact matches
* Normalized matches
* Discrepancies
* Invalid values
* Review requirements
* Resolved/unresolved items
* Final validation status

---

# 15. Final Validation

Before reconciliation is complete, the final dataset is checked for:

* Unresolved discrepancies
* Duplicate records
* Missing required fields
* Invalid values
* Unexpected values
* Missing identifiers
* Structural inconsistencies
* Question-specific validation failures

A reconciliation is complete only when all required discrepancies are resolved and final validation succeeds.

---

# 16. System Architecture

```text
data/
    ↓
Loader
    ↓
Dataset Validator
    ↓
Structure Checker
    ↓
Field Configuration
    ↓
Record Matcher
    ↓
Normalizer
    ↓
Comparison Engine
    ↓
Question-Type Comparators
    ↓
Discrepancy Classifier
    ↓
Review Manager
    ↓
Final Value Resolver
    ↓
Audit Logger
    ↓
Exporter / Reports
```

Main modules:

```text
src/
├── loader.py
├── structure_checker.py
├── matcher.py
├── normalizer.py
├── comparator.py
├── validator.py
├── text_comparator.py
├── review_manager.py
├── audit_logger.py
├── exporter.py
└── main.py
```

Each module has one primary responsibility.

---

# 17. Optional LLM Support

The core reconciliation system remains fully functional without an LLM.

An optional LLM layer may assist with:

* Open-ended text similarity
* Potential transcription detection
* Semantic comparison
* Grouping similar text discrepancies

The LLM does not determine final participant responses.

```text
Deterministic Comparison
        ↓
Text Analysis
        ↓
Optional LLM Assistance
        ↓
Human Review
```

LLM-assisted results remain identifiable in the audit trail.

---

# 18. Testing

Tests are written **alongside each phase**, not at the end, so bugs are caught where they are introduced.

Automated tests cover:

* Dataset loading
* Structure validation
* Record matching
* Duplicate detection
* Normalization
* Single-choice comparison
* Multiple-choice comparison
* Matrix comparison
* Other-response logic
* Open-ended text
* Missing values
* Invalid values
* Review decisions
* Final-value generation
* Audit logging
* Final dataset generation

Synthetic datasets are used before real participant data. The synthetic `CH` dataset is made from the 416 `HS` surveys with **planted, labelled differences** (typos, changed answers, missing Other text, reordered rows, a mistyped code, etc.), so every test knows the correct result in advance.

### Raw-data integrity checks (SHA-256)

Raw data is never pushed to GitHub, so integrity is checked in two places:

| Check | Where / when | What it proves | On failure |
|---|---|---|---|
| **Loader does not modify input** — load a committed *fake* export (`tests/fixtures/`) and compare its SHA-256 before and after | GitHub Actions, on every push (the whole test suite runs) | The code never writes to the files it reads | ❌ on the commit; fix the code |
| **Real raw files unchanged** — recompute the SHA-256 of every file in `data/raw/` and compare with `config/raw_checksums.json` (committed; checksums reveal nothing about the data) | Local Git **pre-push hook**, before every `git push` | The real raw files are exactly the ones the checksums were recorded for | Push is blocked and the changed file is named. Restore the original, or — for a deliberate new export — record the new checksum with one command and commit it, so the change is visible in history |

Optional later: GitHub branch protection so merges are refused while tests fail.

---

# 19. Development Phases

Each phase includes its own tests.

### Phase 0 — Data Preparation ✅ Done

Raw files organized and made read-only, `.gitignore` for participant data, working set of 416 unique `HS` surveys selected, set-aside entries listed with reasons.

### Phase 1 — Data Foundation ⬜ Next

* Loader: read the export (three header rows, all values as text), split by `HS` / `CH`, restrict to the working set, fingerprint raw files
* SHA-256 integrity checks: loader test on fake data in GitHub Actions (every push), `config/raw_checksums.json` + pre-push hook for the real raw files (see §18)
* `questions.json` generated from the `.qsf` (reviewed once by a person)
* Structure comparison between A and B

### Phase 2 — Synthetic Test Data

Synthetic `CH` dataset from the 416 `HS` surveys, with planted, labelled differences.

### Phase 3 — Record Matching

Survey-code clean-up, within-entrant duplicates, pairing A with B, unmatched records.

### Phase 4 — Core Comparison

Normalization, field comparison, question-type handling. First usable output: a list of every disagreement (survey code, question, A value, B value).

### Phase 5 — Text and Special Cases

Open-ended responses, Other fields, similarity analysis.

### Phase 6 — Review System

Review queue (disagreements only), human decisions, final values.

### Phase 7 — Finalization

Audit trail, final dataset, final checks, reports.

### Phase 8 — Real Data

Run on the real `CH` entries once they are available.

---

# 20. Project Principles

The system is built around:

* Raw-data preservation
* Accuracy
* Traceability
* Reproducibility
* Configurable rules
* Question-aware comparison
* Conservative correction
* Human oversight
* Complete auditability
* Separation of detection and correction

The central principle is:

```text
Automate detection and comparison.
Automate only objectively safe normalization.
Keep substantive correction under human control.
Preserve the evidence behind every final value.
```

---

# 21. Completion State

A completed reconciliation run provides:

```text
Two validated source datasets
        ↓
Reliable record mapping
        ↓
Complete field comparison
        ↓
Classified discrepancies
        ↓
Resolved review items
        ↓
Auditable final values
        ↓
Validated final dataset
```

The completed system answers:

* Which records match?
* Which fields differ?
* Which differences are harmless?
* Which differences are substantive?
* Which differences were automatically normalized?
* Which required human review?
* What decision was made?
* What is the final value?
* Why was that value selected?
* Can every change be traced and reproduced?

---

# 22. Open Decisions (for the team)

* How to handle the 63 repeated `HS` survey codes (two different surveys sharing a code vs. duplicate entry)
* The 10 `HS` codes in Qualtrics but not in the paper log, the 6 paper-log numbers not in Qualtrics, and `1-1052` (twice in the paper log, once in Qualtrics)
* Entry conventions to agree with the coworker: initials at the end of every code (` CH`), "N/A" typed only when the respondent wrote it, and how to enter illegible writing or two boxes ticked on a one-answer question
