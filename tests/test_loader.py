"""Loader tests. All run on the fake export in tests/fixtures/, never on real data."""

import json
from dataclasses import replace

import pandas as pd
import pytest

from recon.checksums import checksums_of_dir
from recon.config import EntrantConfig
from recon.loader import (
    CODE_NOT_CHECKABLE, NO_INITIALS, NOT_ON_PAPER_LOG, UNKNOWN_ENTRANT, LoaderError,
    load, parse_survey_code, read_export, write_outputs,
)

HEADER = (
    'ResponseId,QID2,Q1\n'
    'Response ID,Survey code,Question 1\n'
    '"{""ImportId"":""_recordId""}","{""ImportId"":""QID2_TEXT""}","{""ImportId"":""QID3""}"\n'
)


def entry(result_table, n):
    """The row for entry_number n."""
    rows = result_table[result_table["entry_number"] == n]
    assert len(rows) == 1, f"entry {n} appears {len(rows)} times"
    return rows.iloc[0]


# ---------------------------------------------------------------- raw data is never modified

def test_loading_does_not_modify_raw_files(project):
    before = checksums_of_dir(project.raw_dir)
    write_outputs(load(project), project)
    assert checksums_of_dir(project.raw_dir) == before


def test_refuses_to_write_outputs_into_raw_folder(project):
    inside_raw = replace(project, working_dir=project.raw_dir / "out")
    with pytest.raises(LoaderError, match="raw data folder"):
        write_outputs(load(inside_raw), inside_raw)


def test_load_record_notes_raw_file_change_since_last_load(project):
    write_outputs(load(project), project)
    with open(project.raw_dir / "hs_paper_log.txt", "a") as f:
        f.write("500\n")
    record = load(project).record
    assert record["changed_since_last_load"] == [
        "CHANGED:  hs_paper_log.txt does not match its recorded checksum"]


# ---------------------------------------------------------------- header rows

def test_reads_three_header_rows(project):
    columns, data = read_export(project.export_file)
    q1 = columns[columns["column"] == "Q1"].iloc[0]
    assert q1["question_text"] == "How long have you lived here?"
    assert q1["import_id"] == "QID3"
    assert len(data) == 13


def test_rejects_file_with_missing_header_row(write_export):
    # Only rows 1 and 2; the first data row sits where the ImportId row should be.
    config = write_export("ResponseId,QID2\nResponse ID,Survey code\nR_1,1-0001 HS\n")
    with pytest.raises(LoaderError, match="ImportId"):
        load(config)


def test_rejects_file_with_fewer_than_three_rows(write_export):
    with pytest.raises(LoaderError, match="only 2 rows"):
        load(write_export("ResponseId,QID2\nResponse ID,Survey code\n"))


def test_rejects_duplicate_column_names(write_export):
    text = HEADER.replace("ResponseId,QID2,Q1", "ResponseId,QID2,QID2")
    with pytest.raises(LoaderError, match="more than once"):
        load(write_export(text))


def test_rejects_blank_column_name(write_export):
    with pytest.raises(LoaderError, match="blank column names"):
        load(write_export(HEADER.replace("ResponseId,QID2,Q1", "ResponseId,QID2, ")))


def test_rejects_entry_with_wrong_number_of_values(write_export):
    with pytest.raises(LoaderError, match="entry 1 has 2 values"):
        load(write_export(HEADER + "R_1,1-0001 HS\n"))


def test_rejects_non_utf8_file(project):
    project.export_file.write_bytes(HEADER.encode() + "R_1,1-0001 HS,Caf\xe9\n".encode("latin-1"))
    with pytest.raises(LoaderError, match="not UTF-8"):
        load(project)


def test_rejects_export_without_survey_code_column(project):
    with pytest.raises(LoaderError, match="QID99"):
        load(replace(project, id_column="QID99"))


# ---------------------------------------------------------------- values kept exactly as entered

def test_values_are_kept_exactly_as_entered(project):
    a = load(project).datasets["A"]
    first = entry(a, 1)
    assert first["Q1"] == "05"              # not 5 or 5.0
    assert first["Q13"] == "N/A"            # not missing
    assert first["Q2_4_TEXT"] == ""         # blank stays blank
    assert entry(a, 2)["Q2_4_TEXT"] == "  Senior living "   # spacing untouched
    assert all(isinstance(v, str) for v in a.drop(columns=["entry_number", "code_format_ok"])
               .to_numpy().ravel())


def test_text_with_line_breaks_and_accents(project):
    result = load(project)
    assert entry(result.excluded, 8)["Q13"] == "Water in\nbasement"
    assert entry(result.datasets["B"], 11)["Q13"] == "Café"


def test_entry_numbers_are_not_shifted_by_line_breaks(project):
    # Entry 8 contains a line break; the entries after it keep their true positions.
    b = load(project).datasets["B"]
    assert entry(b, 13)["ResponseId"] == "R_fake13"


def test_output_files_round_trip_exactly(project):
    result = load(project)
    write_outputs(result, project)
    reread = pd.read_csv(project.working_dir / "dataset_a.csv", dtype=str,
                         keep_default_na=False, encoding="utf-8-sig")
    original = result.datasets["A"].astype(str)
    pd.testing.assert_frame_equal(reread, original, check_dtype=False)


# ---------------------------------------------------------------- survey code and initials

@pytest.mark.parametrize("raw, expected", [
    ("1-0836 HS", ("1-0836", "HS")),
    ("1-0836 hs", ("1-0836", "HS")),
    ("1-0836HS", ("1-0836", "HS")),
    ("  1-0836   HS ", ("1-0836", "HS")),
    ("1- 0836 HS", ("1-0836", "HS")),
    ("1-0836", ("1-0836", "")),
    ("1-0836 CH", ("1-0836", "CH")),
    ("10619 HS", ("10619", "HS")),       # odd format: kept as written
    ("", ("", "")),
])
def test_parse_survey_code(raw, expected):
    assert parse_survey_code(raw) == expected


def test_entrant_split_and_reasons(project):
    result = load(project)
    assert list(result.datasets["A"]["entry_number"]) == [1, 2, 3, 4]
    assert list(result.datasets["B"]["entry_number"]) == [11, 13]
    reasons = dict(zip(result.excluded["entry_number"], result.excluded["reason"]))
    assert reasons == {
        5: NO_INITIALS,
        6: UNKNOWN_ENTRANT,
        7: "REPEATED_IN_EXPORT(2x); REPEATED_ON_PAPER_LOG(2x)",
        8: "REPEATED_IN_EXPORT(2x); REPEATED_ON_PAPER_LOG(2x)",
        9: NOT_ON_PAPER_LOG,
        10: CODE_NOT_CHECKABLE,
        12: "REPEATED_ON_PAPER_LOG(2x)",
    }


def test_every_entry_is_accounted_for(project):
    result = load(project)
    kept = sum(len(d) for d in result.datasets.values())
    assert kept + len(result.excluded) == result.record["counts"]["entries_in_export"]


def test_codes_are_cleaned_only_for_case_and_spacing(project):
    result = load(project)
    assert entry(result.datasets["A"], 4)["survey_code"] == "1-0004"
    assert entry(result.datasets["A"], 4)["QID2"] == "1- 0004  HS"   # original kept
    odd = entry(result.excluded, 10)
    assert odd["survey_code"] == "10010"                          # never reformatted
    assert not odd["code_format_ok"]


def test_entrant_mapping_comes_from_config(project):
    remapped = replace(project, entrants={
        "HS": EntrantConfig("A", project.entrants["HS"].paper_log),
        "HD": EntrantConfig("B", None),
    })
    result = load(remapped)
    assert list(result.datasets["B"]["entry_number"]) == [6]
    assert entry(result.excluded, 11)["reason"] == UNKNOWN_ENTRANT   # CH no longer known


def test_entrant_without_paper_log_only_needs_unique_codes(project):
    b = load(project).datasets["B"]
    assert set(b["survey_code"]) == {"1-0001", "1-0002"}


# ---------------------------------------------------------------- reports

def test_duplicate_codes_report(project):
    dups = load(project).duplicate_codes
    assert list(dups["entry_number"]) == [7, 8]
    assert set(dups["survey_code"]) == {"1-0007"}
    assert list(dups["times_on_paper_log"]) == [2, 2]
    # Entry 8 differs from entry 7 in Q1, Q9_1 and Q13
    assert list(dups["fields_differing_from_first_entry"]) == ["", 3]


def test_paper_log_numbers_missing_from_export(project):
    missing = load(project).paper_log_not_in_export
    assert list(missing["survey_number"]) == [99]


def test_writes_all_outputs(project):
    write_outputs(load(project), project)
    names = {p.name for p in project.working_dir.iterdir()}
    assert names == {"dataset_a.csv", "dataset_b.csv", "columns.csv", "excluded_entries.csv",
                     "duplicate_codes.csv", "paper_log_not_in_export.csv", "load_record.json"}
    record = json.loads((project.working_dir / "load_record.json").read_text())
    assert set(record["raw_files"]) == {"export.csv", "hs_paper_log.txt", "survey.qsf"}
    assert record["counts"]["dataset_A"] == 4
