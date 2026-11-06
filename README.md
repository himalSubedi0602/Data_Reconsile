# Data Reconcile

Python scripts that find every disagreement in the double-entered **ERC Flood Survey** data
(Qualtrics).

Each paper survey was typed into Qualtrics twice, by two people. The scripts compare the two
entries and list every disagreement. The team checks each one against the paper survey and fixes
the wrong entry directly in Qualtrics, where the analysis is also done. The scripts never modify
the raw data.

See [PLAN.md](PLAN.md) for the full plan.

## Setup

Requires Python 3.11+.

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
git config core.hooksPath scripts/hooks
```

The last line turns on the pre-push hook, which runs the tests before every push.

Survey data is **not** in this repository. Put the raw files in `data/raw/` (see `config/project.json`).

## Usage

```bash
.venv/bin/python -m recon.loader            # load the export(s) → data/working/
.venv/bin/python -m recon.questions         # build the question map → config/questions.json
.venv/bin/python -m recon.compare           # list every disagreement → data/working/differences.xlsx
.venv/bin/streamlit run src/recon/correct_app.py   # open the correction tool in the browser
.venv/bin/python -m recon.checksums verify  # check the raw files are unchanged
.venv/bin/python -m recon.checksums update  # record fingerprints after adding a new raw file
.venv/bin/python -m pytest -q               # run the tests
```

## Set up a new survey

The tool works for any Qualtrics survey typed in twice by two people. Everything is done on screen:
open the tool, and on the home screen use **Set up a new survey**:

1. Give the project a name and upload, from Qualtrics:
   - the survey file: **Tools → Import/Export → Export Survey** (`.qsf`)
   - the responses: **Data & Analysis → Export Data → CSV**, with **Use numeric values**
     (one file, or also one per person if each typed into their own copy)
2. Check the suggested survey code question, the two people's initials and an example code.
3. Optionally add paper logs and a decisions sheet, then click **Prepare project**.

Each project is kept in its own folder, `projects/<name>/` (not in Git: it holds responses), with
the uploaded files, its settings and its saved corrections. The ERC project uses the folders at the
top of this repository. The settings the screen writes, for reference (`config/project.json`):

| Setting | What to put |
|---|---|
| `survey_name` | Name shown in the correction tool |
| `export_file` | The main responses CSV. Entries in it without initials are treated as **online** responses. |
| `extra_export_files` | Other CSVs of the same survey (optional), e.g. one person's own copy. Entries in them without initials show as **no initials**. |
| `qsf_file` | The `.qsf` survey file |
| `raw_dir`, `working_dir` | Leave as `data/raw` and `data/working` |
| `id_column` | Export column holding the survey code, e.g. `QID2` |
| `code_pattern` | What a correct survey code looks like, as a regular expression, e.g. `^\\d+-\\d{4}$` for `1-0235`. Each person types the code followed by their initials (`1-0235 HS`). |
| `code_example` | One correct code, shown as a hint, e.g. `1-0235` |
| `entrants` | The two people's initials, each with `dataset` `A` or `B` and an optional `paper_log` (a text file of the survey numbers they typed, separated by spaces or new lines) |
| `decisions` | Optional: a sheet of decisions made about specific surveys, shown in the tool. Give `file` (.xlsx), `sheet`, `label` (who made them, e.g. `W&J`), `survey_columns` (the column(s) that identify the survey, e.g. location and number), `question_column`, `decision_column` and `notes_column`. A question cell starting with `Q27` is shown at question 27. |

## Outputs

| File | What it is |
|---|---|
| `data/working/dataset_a.csv`, `dataset_b.csv` | Each person's entries used for the comparison |
| `data/working/excluded_entries.csv` | Entries set aside, with the reason |
| `data/working/load_record.json` | Raw-file fingerprints and counts for each load |
| `data/working/differences.xlsx` | One row per disagreement (both answers, both ResponseIds), plus surveys entered by only one person |
| `config/questions.json` | What every column means (not in Git: contains the survey wording) |

## Tech

Python · pandas · pytest · Qualtrics CSV exports
