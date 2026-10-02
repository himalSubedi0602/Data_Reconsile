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
.venv/bin/python -m recon.checksums verify  # check the raw files are unchanged
.venv/bin/python -m recon.checksums update  # record fingerprints after adding a new raw file
.venv/bin/python -m pytest -q               # run the tests
```

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
