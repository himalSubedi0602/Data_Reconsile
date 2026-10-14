# data_reconcile: Correction Plan

## 1. Objective

Produce **one correct record for every survey** of the **ERC Flood Survey**, checked against the original paper, and deliver it as a **CSV in Qualtrics answer codes (values)** for analysis in Qualtrics or R.

The paper surveys were typed into Qualtrics twice:

* **Dataset A** = entries by Himal (survey code ends in `HS`)
* **Dataset B** = entries by Caleb (survey code ends in `CH`, in his own copy of the survey)

Some responses were also filled out **online by participants** themselves (no initials).

The work is done with a **correction tool** that opens any survey, shows both entries side by side, and lets the corrector fix the record to match the paper. Julia's three validation checks are built into the plan.

---

# 2. Principles

* **The paper survey decides every answer.** When the paper itself is unclear, the **W&J decisions** (team workbook) apply; new cases go to Julia and Whitney and are added there.
* The original Qualtrics exports are **never modified**. Each corrected record is rebuilt from the chosen entry plus the recorded changes.
* **Every change is recorded**: survey, question, old value, new value, time.
* Only **valid answer options** can be entered, so no impossible codes.
* Unclear survey codes are **never guessed**; they are resolved by the team.
* Participant data is never committed to Git.

---

# 3. Data

```text
data/raw/                                          ← read-only originals (not in Git)
├── erc_flood_qualtrics_export_2026-09-28.csv      ← main export: Himal's entries + online responses
├── erc_flood_qualtrics_export_ch_2026-10-12.csv   ← Caleb's entries (complete)
├── erc_flood_qualtrics_export_ch_2026-09-30.csv   ← Caleb's earlier export (kept as record)
├── erc_flood_survey_definition.qsf / _ch.qsf      ← survey structure
├── hs_paper_log.txt                               ← Himal's paper log
└── envelope_data_record_2026-10-14.xlsx           ← team workbook: Master list, tracking logs, W&J decisions
data/working/                                      ← generated reports (not in Git)
data/corrections/                                  ← correction log + CSVs per round (not in Git)
```

---

# 4. What is already done

* **Load & understand:** both exports read exactly as entered; entries split by initials; unclear entries set aside with a reason; every column's question, options and role known (question map from the `.qsf`).
* **Compare:** for every survey typed by both people, every answer compared. Result (Oct 12): **408 surveys compared, 116 match completely, 292 have 896 disagreements**. Reports: `differences.xlsx`, `survey_problems.xlsx`.

---

# 5. The correction tool

1. **Find any survey**: search by code or browse lists of all surveys (entered by Himal, Caleb, both, or online by participants), with markers for: flagged by the comparison, flagged by W&J, and status (not started / in progress / done).
2. **Open a survey**: laid out like the paper questionnaire, pre-filled. For **every question both entries are shown side by side** (Himal's and Caleb's); questions where they differ are highlighted, and matching answers are shown too, so a shared mistake can still be caught. W&J decisions appear next to the question they apply to. If only one entry exists, that entry is shown.
3. **Correct**: pick the entry most in line with the paper, then change any answer to match the paper: another option, tick/untick boxes, change a grid rating, edit or clear text, or clear any answer.
4. **Save** every change to the log; **mark the survey done** once checked against the paper. Work can stop and resume any time.
5. **Create a CSV**: one record per finished survey, numeric answer codes, in Qualtrics' import layout. Not created while a survey in it is unfinished.

---

# 6. Order of work

| Round | Surveys | Result |
|---|---|---|
| **1** | Codes **not repeated**, flagged by the comparison or by W&J (**306**) | CSV after round 1 |
| **2** | Codes **repeated** during entry (after discussing with Julia and Whitney how to separate them) | CSV after round 2 |
| **3** | All remaining surveys entered by Himal or Caleb that were **never opened or flagged** | CSV after round 3 |
| **4** | **Participants' online responses** | **Final CSV with all the data** |

Each round's CSV contains every survey finished so far, so it grows round by round; the CSV after round 4 is the complete dataset.

---

# 7. Validation (requested by Julia)

| # | When | How |
|---|---|---|
| **1. Survey list** | Before correcting | Compare all surveys with the **Master** tab and **both tracking logs** in the team workbook; report missing, extra, repeated or mistyped codes; spot-check a few paper surveys; team sign-off before correcting starts. |
| **2. Corrections vs paper** | After each round | **10 surveys picked at random** (including some never flagged); each one's final answers printed in words and checked against the paper by Himal; any mistake → fix it and check 10 more. |
| **3. Import** | After the final CSV | Import into a **copy** of the survey in Qualtrics (a few test responses first), export again and compare automatically with the final CSV (**zero differences**); a few surveys checked by eye. |

---

# 8. Stages

1. Validation 1 (survey list) and team sign-off
2. Build the correction tool; try it on a few real surveys
3. Round 1 → Validation 2 → CSV
4. Round 2 → Validation 2 → CSV
5. Round 3 → Validation 2 → CSV
6. Round 4 → Validation 2 → **final CSV**
7. Validation 3 (import into a Qualtrics copy)
8. Hand over for analysis (Qualtrics or R); keep the originals, the correction log, the CSVs and the validation results

---

# 9. Testing

Tests cover only what could silently give wrong data:

* raw files changing (checksum check before every push)
* values being changed or codes reformatted on load
* a real disagreement being treated as a match
* a correction landing in the wrong survey or question, or an untouched answer changing in the CSV
* an invalid answer code being written

---

# 10. Git workflow

* One branch and one pull request per stage; GitHub Actions runs the tests on every push.
* A pre-push hook runs all tests, including the raw-data checksum check, and blocks the push if any fail.
* No survey data, CSV or Excel file is ever committed (`.gitignore`).
