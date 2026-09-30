# Data Reconcile

Python scripts that clean the double-entered **ERC Flood Survey** data (Qualtrics) and produce a
final dataset for analysis in R.

Each paper survey was typed into Qualtrics twice, by two people. The scripts compare the two
entries, list every disagreement for the team to resolve against the paper survey, and build the
final dataset from the agreed answers and the team's corrections. Raw data is never modified.

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
.venv/bin/python -m recon.checksums verify  # check the raw files are unchanged
.venv/bin/python -m recon.checksums update  # record fingerprints after adding a new raw file
.venv/bin/python -m pytest -q               # run the tests
```

More steps (comparison, final dataset) are added as the cleanup progresses.

## Outputs

| File | What it is |
|---|---|
| `data/working/dataset_a.csv`, `dataset_b.csv` | Each person's entries used for the comparison |
| `data/working/excluded_entries.csv` | Entries set aside, with the reason |
| `data/working/load_record.json` | Raw-file fingerprints and counts for each load |
| `config/questions.json` | What every column means (not in Git: contains the survey wording) |

## Tech

Python · pandas · pytest · Qualtrics CSV exports · R (for the analysis)
