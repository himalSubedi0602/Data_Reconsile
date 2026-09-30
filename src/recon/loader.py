"""Load the Qualtrics export into Dataset A and Dataset B.

The loader only reads the raw files. It never changes, fixes or interprets an answer:
every value is kept as the exact text in the export.

Steps:
  1. Fingerprint the raw files (SHA-256).
  2. Read and check the three Qualtrics header rows.
  3. Read every value as text, exactly as entered.
  4. Label every entry with entry_number (its position in the export) and keep ResponseId.
  5. Split the survey code into code + entrant initials.
  6. Assign entries to A or B by initials (config/project.json).
  7. Apply the working-set rule; everything left out is listed with its reason.
  8. Save the outputs to data/working/ and write load_record.json.

Run from the project root:  python -m recon.loader
"""

import csv
import json
import platform
import re
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

import recon
from recon.checksums import checksums_of_dir, sha256_of
from recon.config import DATASETS, DEFAULT_CONFIG, ProjectConfig, load_config

HEADER_ROWS = 3  # Qualtrics: column name, question text, {"ImportId": ...}

# Columns the loader adds in front of the original export columns.
ENTRY_NUMBER = "entry_number"   # position within its export file
SOURCE_FILE = "source_file"
SURVEY_CODE = "survey_code"
ENTRANT = "entrant"
CODE_FORMAT_OK = "code_format_ok"
LOADER_COLUMNS = [ENTRY_NUMBER, SOURCE_FILE, SURVEY_CODE, ENTRANT, CODE_FORMAT_OK]

# Reasons an entry is left out of A and B.
NO_INITIALS = "NO_INITIALS"
UNKNOWN_ENTRANT = "UNKNOWN_ENTRANT"
REPEATED_IN_EXPORT = "REPEATED_IN_EXPORT"
NOT_ON_PAPER_LOG = "NOT_ON_PAPER_LOG"
REPEATED_ON_PAPER_LOG = "REPEATED_ON_PAPER_LOG"
CODE_NOT_CHECKABLE = "CODE_FORMAT_NOT_CHECKABLE_AGAINST_PAPER_LOG"

# Survey code, then optional spacing, then the entrant's initials at the very end.
CODE_AND_INITIALS = re.compile(r"^(?P<code>.*\d)\s*(?P<initials>[A-Za-z]+)$")


class LoaderError(Exception):
    """The export can't be loaded safely. The message says why."""


@dataclass
class LoadResult:
    columns: pd.DataFrame          # one row per export column: name, question text, ImportId
    datasets: dict[str, pd.DataFrame]   # "A" / "B" -> entries kept for comparison
    excluded: pd.DataFrame         # every entry not in A or B, with the reason
    duplicate_codes: pd.DataFrame  # codes entered more than once by the same entrant
    paper_log_not_in_export: pd.DataFrame
    record: dict                   # contents of load_record.json


# ---------------------------------------------------------------- steps 2–4

def read_export(path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Read a Qualtrics CSV export. Returns (column info, entries), all values as text."""
    path = Path(path)
    try:
        with open(path, newline="", encoding="utf-8-sig") as f:
            rows = list(csv.reader(f))
    except FileNotFoundError:
        raise LoaderError(f"Export not found: {path}") from None
    except UnicodeDecodeError as e:
        raise LoaderError(f"{path.name} is not UTF-8 text ({e}). "
                          "Export it from Qualtrics as CSV (UTF-8).") from None

    while rows and rows[-1] == []:      # trailing blank lines
        rows.pop()
    if len(rows) < HEADER_ROWS:
        raise LoaderError(f"{path.name}: expected {HEADER_ROWS} Qualtrics header rows, "
                          f"but the file has only {len(rows)} rows.")

    names, texts, id_row = rows[:HEADER_ROWS]
    if not len(names) == len(texts) == len(id_row):
        raise LoaderError(f"{path.name}: the three header rows have different lengths "
                          f"({len(names)}, {len(texts)}, {len(id_row)}).")

    blank = [i + 1 for i, n in enumerate(names) if not n.strip()]
    if blank:
        raise LoaderError(f"{path.name}: header row 1 has blank column names at "
                          f"positions {blank}.")
    repeated = sorted(n for n, c in Counter(names).items() if c > 1)
    if repeated:
        raise LoaderError(f"{path.name}: column names appear more than once: {repeated}. "
                          "Columns can't be told apart.")

    import_ids, choice_ids = [], []
    for i, cell in enumerate(id_row):
        try:
            meta = json.loads(cell)
            import_ids.append(meta["ImportId"])
            choice_ids.append(meta.get("choiceId", ""))   # set on check-all option columns
        except (json.JSONDecodeError, KeyError, TypeError):
            raise LoaderError(
                f"{path.name}: header row 3, column {i + 1} ({names[i]}) is not a Qualtrics "
                f"ImportId: {cell[:60]!r}. Is this a Qualtrics export with all three "
                "header rows (export option 'Use numeric values', CSV)?") from None

    entries = rows[HEADER_ROWS:]
    for n, row in enumerate(entries, start=1):
        if len(row) != len(names):
            raise LoaderError(f"{path.name}: entry {n} has {len(row)} values but the header "
                              f"has {len(names)} columns. The file may be damaged.")

    columns = pd.DataFrame({
        "position": range(1, len(names) + 1),
        "column": names,
        "question_text": texts,
        "import_id": import_ids,
        "choice_id": choice_ids,
    })
    data = pd.DataFrame(entries, columns=names, dtype=object)
    data.insert(0, ENTRY_NUMBER, range(1, len(data) + 1))
    return columns, data


# ---------------------------------------------------------------- step 5

def parse_survey_code(raw: str) -> tuple[str, str]:
    """'1-0836 HS' -> ('1-0836', 'HS'). Only case and spacing are cleaned.

    Returns initials '' when the code doesn't end in letters.
    """
    text = "".join(raw.split())          # drop all spacing, including line breaks
    m = CODE_AND_INITIALS.match(text)
    if not m:
        return text, ""
    return m["code"], m["initials"].upper()


def read_paper_log(path) -> Counter:
    """Survey numbers in a paper log (whitespace-separated), with how often each appears."""
    path = Path(path)
    try:
        tokens = path.read_text(encoding="utf-8").split()
    except FileNotFoundError:
        raise LoaderError(f"Paper log not found: {path}") from None
    bad = [t for t in tokens if not t.isdigit()]
    if bad:
        raise LoaderError(f"{path.name}: expected only survey numbers, found {bad[:5]}")
    return Counter(int(t) for t in tokens)


def paper_log_number(code: str) -> int:
    """'1-0836' -> 836: the number written in the paper log."""
    return int(code.rsplit("-", 1)[1])


# ---------------------------------------------------------------- steps 6–7

def _working_set_reasons(entries: pd.DataFrame, paper_log: Counter | None) -> pd.Series:
    """Why each of one entrant's entries is left out ('' = kept)."""
    times_in_export = entries[SURVEY_CODE].map(entries[SURVEY_CODE].value_counts())

    def reasons(row, repeats):
        out = []
        if repeats > 1:
            out.append(f"{REPEATED_IN_EXPORT}({repeats}x)")
        if paper_log is not None:
            if not row[CODE_FORMAT_OK]:
                out.append(CODE_NOT_CHECKABLE)
            else:
                on_log = paper_log.get(paper_log_number(row[SURVEY_CODE]), 0)
                if on_log == 0:
                    out.append(NOT_ON_PAPER_LOG)
                elif on_log > 1:
                    out.append(f"{REPEATED_ON_PAPER_LOG}({on_log}x)")
        return "; ".join(out)

    return pd.Series(
        [reasons(row, n) for (_, row), n in zip(entries.iterrows(), times_in_export)],
        index=entries.index, dtype=object,
    )


def _duplicate_codes(entries: pd.DataFrame, answer_columns: list[str],
                     paper_log: Counter | None) -> pd.DataFrame:
    """Codes one entrant entered more than once, one row per entry."""
    rows = []
    repeated = entries[entries[SURVEY_CODE].duplicated(keep=False)]
    for code, group in repeated.groupby(SURVEY_CODE, sort=True):
        first = group.iloc[0]
        for i, (_, row) in enumerate(group.iterrows()):
            differing = sum(row[c].strip() != first[c].strip() for c in answer_columns)
            rows.append({
                ENTRANT: row[ENTRANT],
                SURVEY_CODE: code,
                "times_in_export": len(group),
                ENTRY_NUMBER: row[ENTRY_NUMBER],
                "ResponseId": row.get("ResponseId", ""),
                "RecordedDate": row.get("RecordedDate", ""),
                "Finished": row.get("Finished", ""),
                "fields_differing_from_first_entry": "" if i == 0 else differing,
                "times_on_paper_log": (paper_log.get(paper_log_number(code), 0)
                                       if paper_log is not None and row[CODE_FORMAT_OK]
                                       else ""),
            })
    return pd.DataFrame(rows, columns=[
        ENTRANT, SURVEY_CODE, "times_in_export", ENTRY_NUMBER, "ResponseId", "RecordedDate",
        "Finished", "fields_differing_from_first_entry", "times_on_paper_log"])


# ---------------------------------------------------------------- step 1.15: several exports

def structure_problems(first: pd.DataFrame, other: pd.DataFrame) -> list[str]:
    """Differences between two exports' columns: missing, extra, or a different internal ID."""
    a, b = list(first["column"]), list(other["column"])
    problems = [f"missing column: {c}" for c in a if c not in b]
    problems += [f"extra column: {c}" for c in b if c not in a]
    ids = ["column", "import_id", "choice_id"]
    for r in first[ids].merge(other[ids], on="column", suffixes=("", "_2")).itertuples():
        if (r.import_id, r.choice_id) != (r.import_id_2, r.choice_id_2):
            problems.append(f"{r.column}: internal ID differs ({r.import_id} vs {r.import_id_2})")
    return problems


def _drop_repeated_responses(data: pd.DataFrame) -> pd.DataFrame:
    """A response found in two export files is kept once. The same ResponseId with
    different answers stops the load."""
    unique = data.drop_duplicates([c for c in data.columns if c not in (ENTRY_NUMBER, SOURCE_FILE)])
    clash = unique.loc[unique["ResponseId"].duplicated(), "ResponseId"]
    if len(clash):
        raise LoaderError(f"Same ResponseId with different answers in two files: {sorted(set(clash))}")
    return unique.reset_index(drop=True)


# ---------------------------------------------------------------- whole load

def load(config: ProjectConfig) -> LoadResult:
    """Run steps 1–7 in memory. Nothing is written."""
    # Step 1: fingerprints
    raw_checksums = checksums_of_dir(config.raw_dir) if config.raw_dir.is_dir() else {}

    # Steps 2–4, for the main export and any extra ones (e.g. the coworker's)
    columns, data = read_export(config.export_file)
    data.insert(1, SOURCE_FILE, config.export_file.name)
    for path in config.extra_export_files:
        more_columns, more = read_export(path)
        problems = structure_problems(columns, more_columns)
        if problems:
            raise LoaderError(f"{path.name} doesn't have the same columns as "
                              f"{config.export_file.name}:\n  " + "\n  ".join(problems))
        more.insert(1, SOURCE_FILE, path.name)
        data = pd.concat([data, more], ignore_index=True)
    if config.id_column not in data.columns:
        raise LoaderError(f"Survey-code column {config.id_column!r} is not in the export.")
    in_files = len(data)
    data = _drop_repeated_responses(data)

    # Step 5
    parsed = data[config.id_column].map(parse_survey_code)
    data.insert(2, SURVEY_CODE, parsed.str[0])
    data.insert(3, ENTRANT, parsed.str[1])
    pattern = re.compile(config.code_pattern)
    data.insert(4, CODE_FORMAT_OK, data[SURVEY_CODE].map(lambda c: bool(pattern.match(c))))

    # Steps 6–7
    reason = pd.Series("", index=data.index, dtype=object)
    reason[data[ENTRANT] == ""] = NO_INITIALS
    known = data[ENTRANT].isin(list(config.entrants))
    reason[(data[ENTRANT] != "") & ~known] = UNKNOWN_ENTRANT

    # Answer columns: everything Qualtrics exports from a survey question (ImportId QID…),
    # except the survey code itself. Used only to describe repeated codes.
    answer_columns = [c for c, i in zip(columns["column"], columns["import_id"])
                      if i.startswith("QID") and c != config.id_column]

    dataset_of = pd.Series("", index=data.index, dtype=object)
    datasets, duplicate_reports, log_missing = {}, [], []
    for initials, entrant in config.entrants.items():
        mine = data[data[ENTRANT] == initials]
        dataset_of[mine.index] = entrant.dataset
        log = read_paper_log(entrant.paper_log) if entrant.paper_log else None
        reason[mine.index] = _working_set_reasons(mine, log)
        duplicate_reports.append(_duplicate_codes(mine, answer_columns, log))
        if log is not None:
            in_export = {paper_log_number(c) for c in mine.loc[mine[CODE_FORMAT_OK], SURVEY_CODE]}
            log_missing += [{ENTRANT: initials, "survey_number": n, "times_on_paper_log": k}
                            for n, k in sorted(log.items()) if n not in in_export]

    kept = reason == ""
    for dataset in DATASETS:
        datasets[dataset] = data[kept & (dataset_of == dataset)].reset_index(drop=True)

    excluded = data[~kept].copy()
    excluded.insert(len(LOADER_COLUMNS), "dataset", dataset_of[~kept])
    excluded.insert(len(LOADER_COLUMNS) + 1, "reason", reason[~kept])
    excluded = excluded.reset_index(drop=True)

    record = {
        "loaded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "loader_version": recon.__version__,
        "python": platform.python_version(),
        "pandas": pd.__version__,
        "config_file": config.path.as_posix(),
        "config_sha256": sha256_of(config.path) if config.path.is_file() else None,
        "export_files": [p.name for p in (config.export_file, *config.extra_export_files)],
        "raw_files": raw_checksums,
        "counts": {
            "entries_in_export": len(data),
            "repeated_responses_dropped": in_files - len(data),
            "columns_in_export": len(columns),
            "entries_by_initials": {k or "(none)": int(v) for k, v in
                                    data[ENTRANT].value_counts().sort_index().items()},
            "dataset_A": len(datasets["A"]),
            "dataset_B": len(datasets["B"]),
            "excluded": len(excluded),
            "excluded_by_reason": {k: int(v) for k, v in
                                   excluded["reason"].value_counts().sort_index().items()},
            "code_format_flagged_in_A_or_B": int(sum((~d[CODE_FORMAT_OK]).sum()
                                                     for d in datasets.values())),
        },
    }
    return LoadResult(
        columns=columns,
        datasets=datasets,
        excluded=excluded,
        duplicate_codes=pd.concat(duplicate_reports, ignore_index=True),
        paper_log_not_in_export=pd.DataFrame(
            log_missing, columns=[ENTRANT, "survey_number", "times_on_paper_log"]),
        record=record,
    )


# ---------------------------------------------------------------- step 8

def write_outputs(result: LoadResult, config: ProjectConfig) -> list[Path]:
    """Write everything to the working folder. Refuses to write inside the raw folder."""
    out = config.working_dir.resolve()
    raw = config.raw_dir.resolve()
    if out == raw or raw in out.parents:
        raise LoaderError(f"Refusing to write outputs inside the raw data folder: {out}")
    out.mkdir(parents=True, exist_ok=True)

    tables = {
        "dataset_a.csv": result.datasets["A"],
        "dataset_b.csv": result.datasets["B"],
        "columns.csv": result.columns,
        "excluded_entries.csv": result.excluded,
        "duplicate_codes.csv": result.duplicate_codes,
        "paper_log_not_in_export.csv": result.paper_log_not_in_export,
    }
    written = []
    for name, table in tables.items():
        # utf-8-sig so Excel shows accented characters correctly
        table.to_csv(out / name, index=False, encoding="utf-8-sig")
        written.append(out / name)
    record_path = out / "load_record.json"
    record_path.write_text(json.dumps(result.record, indent=2) + "\n", encoding="utf-8")
    written.append(record_path)
    return written


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    config = load_config(argv[0] if argv else DEFAULT_CONFIG)
    try:
        result = load(config)
    except LoaderError as e:
        print(f"LOAD STOPPED: {e}")
        return 1
    write_outputs(result, config)

    c = result.record["counts"]
    print(f"Loaded {c['entries_in_export']} entries, {c['columns_in_export']} columns "
          f"from {config.export_file.name}")
    print(f"  Dataset A: {c['dataset_A']}")
    print(f"  Dataset B: {c['dataset_B']}")
    print(f"  Excluded:  {c['excluded']}")
    for r, n in c["excluded_by_reason"].items():
        print(f"    {n:4d}  {r}")
    if c["code_format_flagged_in_A_or_B"]:
        print(f"  Codes in an unusual format (kept, flagged): {c['code_format_flagged_in_A_or_B']}")
    print(f"Outputs written to {config.working_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
