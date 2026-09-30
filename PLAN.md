# data_reconcile: Data Cleanup Plan

## 1. Objective

Clean the double-entered **ERC Flood Survey** data and produce one validated dataset for analysis in R.

The same paper surveys were typed into Qualtrics twice, by two people:

* **Dataset A** = entries by Himal (survey code ends in `HS`)
* **Dataset B** = entries by the coworker (survey code ends in `CH`)

The cleanup compares the two entries of each survey, resolves every disagreement against the paper survey, and produces:

```text
final_dataset.csv   one row per survey, answers as Qualtrics numeric codes
codebook.csv        column → question text → meaning of each code
```

This is a **one-off cleanup for this project**, done with a few short Python scripts. It is not a general-purpose tool.

---

# 2. Principles

* Raw data is **never modified**. Raw files are read-only and fingerprinted (SHA-256).
* Fields where both entries agree are accepted as entered.
* Harmless differences (extra spaces, capitalization) count as agreement and are never shown for review.
* **Every real disagreement is decided by a person**, using the paper survey. No script picks a value.
* Unclear entries (repeated codes, missing initials, etc.) are **set aside with a reason**, never silently dropped or merged.
* Every step can be re-run and gives the same result.
* Participant data is never committed to Git.

---

# 3. Data

```text
data/
├── raw/                                           ← read-only originals (not in Git)
│   ├── erc_flood_qualtrics_export_2026-09-28.csv  ← main Qualtrics export
│   ├── <coworker export>.csv                      ← CH entries, if exported separately
│   ├── erc_flood_survey_definition.qsf            ← survey structure
│   └── hs_paper_log.txt                           ← Himal's paper log of survey numbers
└── working/                                       ← everything generated (not in Git)
```

* Exports use **numeric values**, with multi-value fields **split into columns**.
* `config/questions.json` (the question map) is also kept out of Git, because it contains the survey wording.

---

# 4. Workflow

```text
Qualtrics export(s) ──► 1. Load & understand ──► 2. Add CH data ──► 3. Compare HS vs CH
                                                                          │
                                                                          ▼
          R analysis ◄── 5. Final dataset + codebook ◄── 4. Team resolves disagreements
```

## Phase 1: Load & understand ✅

* Read the export with its three Qualtrics header rows, keeping every value exactly as entered.
* Split entries by the initials at the end of the survey code (`HS` → A, `CH` → B).
* Working set for A: codes that appear **exactly once** in Qualtrics **and** exactly once in the paper log (**416 surveys**). The rest are set aside with a reason; entries with no initials are ignored for now.
* Build the question map from the `.qsf`: every column's question, option or grid row, role (`COMPARE` / `METADATA` / `IDENTIFIER`). It stops if the export and `.qsf` don't line up.
* Accept a separate coworker export: it must have exactly the same columns and internal IDs, and a response found in both files is kept once.

## Phase 2: Add the coworker's (`CH`) data

* Put the coworker's CSV in `data/raw/`, make it read-only, list it in `config/project.json`, and record its fingerprint.
* Run the loader and check how many `CH` entries there are and how many are set aside.
* `CH` data arrives in batches; each new file repeats this phase.

## Phase 3: Compare

* Pair surveys entered by **both** people (by survey code). List surveys only one person entered.
* Compare every `COMPARE` column; harmless differences count as a match.
* Write **`differences.xlsx`**: one row per disagreement, with the survey code, question, answer labels, both values, and empty *correct value* and *notes* columns.
* Re-running (after more `CH` data arrives) **keeps corrections already filled in**.

## Phase 4: Resolve (team)

* Check each disagreement against the paper survey and fill in the correct value.
* Decide what to do with the set-aside and no-initials codes (see the Survey Code Summary tab in the team's master workbook).

## Phase 5: Final dataset

* `final_dataset.csv`: agreed answers + the team's corrections. The script **stops** if any disagreement is still unresolved.
* `codebook.csv`: built from the approved question map.

## Phase 6: Analysis (R, outside this plan)

---

# 5. Testing

Tests only cover mistakes that would **silently give wrong data**:

* raw files changing (checksum check before every push)
* codes being reformatted, or values being changed on load
* a real disagreement being treated as a match
* a correction landing in the wrong survey or column

Tests use small fake files in `tests/fixtures/`. Tests on the real data run only locally (the data is never on GitHub).

---

# 6. Git workflow

* One branch and one pull request per phase; GitHub Actions runs the tests on every push.
* A pre-push hook runs all tests, including the raw-data checksum check, and blocks the push if any fail.

---

# 7. Open decisions (for the team)

* The 63 repeated `HS` survey codes (two surveys sharing a code, or a duplicate entry?)
* The 10 `HS` codes in Qualtrics but not in the paper log, the 6 paper-log numbers not in Qualtrics, and `1-1052` (twice in the paper log, once in Qualtrics)
* The 168 codes entered without initials
* Entry conventions with the coworker: initials at the end of every code (` CH`), "N/A" only when the respondent wrote it, how to enter illegible writing or two boxes ticked on a one-answer question

---

# 8. Possible later work

A general reconciliation tool for other surveys may be built later as a **separate project**, reusing the loader and question map from this one.
