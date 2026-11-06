import csv
from dataclasses import replace
from pathlib import Path

import pandas as pd
import pytest

from recon.config import ProjectConfig
from recon.corrections import Project
from test_compare import QMAP

CONFIG = ProjectConfig(path=Path("project.json"), export_file=Path("main.csv"), qsf_file=Path("survey.qsf"),
                       raw_dir=Path("raw"), working_dir=Path("working"), id_column="QID2",
                       code_pattern=r"^\d+-\d{4}$", entrants={}, code_example="1-0235")


def _project(tmp_path):
    hs = pd.DataFrame({"survey_code": ["1-0001", "1-0002"], "ResponseId": ["R_a1", "R_a2"],
                       "Q1": ["2", "2"], "Q9_1": ["1", ""], "Q9_6_TEXT": ["shed", ""], "Q13": ["ok", ""]})
    ch = pd.DataFrame({"survey_code": ["1-0001"], "ResponseId": ["R_b1"],
                       "Q1": ["3"], "Q9_1": ["1"], "Q9_6_TEXT": ["shed"], "Q13": ["ok"]})
    entries = {"HS": hs.set_index("survey_code"), "CH": ch.set_index("survey_code")}
    header = pd.DataFrame({"column": ["QID2", "Q1", "Q9_1", "Q9_6_TEXT", "Q13", "StartDate"],
                           "question_text": ["Code", "How long?", "Storage", "Other", "Details", "Start"],
                           "import_id": ["QID2_TEXT", "QID3", "QID12", "QID12_6_TEXT", "QID42_TEXT", "startDate"],
                           "choice_id": ["", "", "1", "", "", ""]})
    qmap = {**QMAP, "columns": QMAP["columns"] + [
        {"column": "QID2", "qid": "QID2", "choice": "", "is_text": True, "role": "IDENTIFIER"}]}
    excluded = pd.DataFrame({"survey_code": ["1-0003", "1-0003", "1-0002"], "entrant": ["HS", "HS", ""],
                             "ResponseId": ["R_a3", "R_a4", "R_o2"], "source_file": ["main.csv"] * 3,
                             "RecordedDate": ["2026-09-09 13:27", "2026-09-16 13:57", "2026-08-01 10:00"],
                             "Q1": ["2", "3", "4"], "Q9_1": [""] * 3, "Q9_6_TEXT": [""] * 3, "Q13": [""] * 3,
                             "reason": ["REPEATED_IN_EXPORT(2x)"] * 2 + ["NO_INITIALS"]})
    return Project(config=CONFIG, qmap=qmap, entries=entries, store=tmp_path, decisions={}, header=header,
                   excluded=excluded)


def test_changes_land_in_the_right_place_and_nothing_else_changes(tmp_path):
    p = _project(tmp_path)
    assert p.disagree("1-0001", "Q1") and not p.disagree("1-0001", "Q13")
    assert list(p.related_entries("1-0001")["Entered by"]) == ["CH", "HS"]
    notes = p.difference_notes("1-0001")
    assert list(zip(notes["Question"], notes["HS"], notes["CH"], notes["Difference"])) == [
        ("Q1", "2 = 1-5 years", "3 = 6-10 years", "Different answer")]
    assert p.surveys().set_index("survey_code").loc["1-0002", "entered_by"] == "HS + online"
    assert p.record("1-0002", "online")["Q1"] == "4"                   # an online response can be corrected too
    # A code typed twice (both entries set aside) can still be corrected, from either entry.
    assert p.surveys().set_index("survey_code").loc["1-0003", "entered_by"] == "HS ×2"
    assert p.record("1-0003", "HS 2026-09-16 13:57")["Q1"] == "3"
    # The other paper with that code gets its own code, corrected from the same entries; kept on reopening.
    with pytest.raises(ValueError, match="must be 1-0003"):
        p.add_code("1-0004-2", "1-0003")
    p.add_code("1-0003-2", "1-0003")
    with pytest.raises(ValueError, match="already exists"):
        p.add_code("1-0003-2", "1-0003")
    assert _project(tmp_path).record("1-0003-2", "HS 2026-09-09 13:27 (1-0003)")["Q1"] == "2"
    # A survey never typed in can be filled in from a blank form; kept on reopening.
    with pytest.raises(ValueError, match="already exists"):
        p.new_survey("1-0001")
    p.new_survey("1-0009")
    p.save("1-0009", "blank", p.record("1-0009", "blank") | {"Q1": "2"})
    assert _project(tmp_path).record("1-0009", "blank") == {"Q1": "2", "Q9_1": "", "Q9_6_TEXT": "", "Q13": ""}

    new = p.record("1-0001", "HS") | {"Q1": "3", "Q13": ""}          # correct Q1, clear Q13
    assert p.save("1-0001", "HS", new) == 2
    assert p.record("1-0001", "HS") == {"Q1": "3", "Q9_1": "1", "Q9_6_TEXT": "shed", "Q13": ""}
    assert p.record("1-0002", "HS")["Q1"] == "2"                      # other survey untouched
    assert p.record("1-0001", "CH")["Q13"] == "ok"                    # changes belong to the HS start only
    assert p.save("1-0001", "HS", p.record("1-0001", "HS")) == 0      # nothing new, nothing logged

    with pytest.raises(ValueError, match="not a valid answer"):
        p.save("1-0001", "HS", p.record("1-0001", "HS") | {"Q1": "9"})
    p.set_status("1-0001", "HS", "done")
    assert p.surveys().set_index("survey_code").loc["1-0001", "status"] == "done"


def test_export_writes_one_corrected_row_per_done_survey(tmp_path):
    p = _project(tmp_path)
    p.save("1-0001", "CH", p.record("1-0001", "CH") | {"Q9_6_TEXT": "garden shed"})
    p.set_status("1-0001", "CH", "done")
    p.save("1-0002", "HS", p.record("1-0002", "HS") | {"Q1": "3"})     # in progress: not exported

    assert p.export(tmp_path / "out.csv") == 1
    with open(tmp_path / "out.csv", newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    assert rows[0] == ["QID2", "Q1", "Q9_1", "Q9_6_TEXT", "Q13"]      # answer columns only, export order
    assert rows[2][2] == '{"ImportId":"QID12","choiceId":"1"}'
    assert rows[3] == ["1-0001", "3", "1", "garden shed", "ok"]         # CH entry + the one change
    assert len(rows) == 4

    assert p.random_check(tmp_path / "check.xlsx", seed=1) == ["1-0001"]


def test_edge_cases(tmp_path):
    grid = {"tag": "Q11", "kind": "grid", "text": "How often?", "rows": {"8": "Property damage"},
            "scale": {"1": "Always", "5": "Never"}}
    qmap = {"questions": {**QMAP["questions"], "QID15": grid}, "columns": [
        {"column": "QID2", "qid": "QID2", "choice": "", "is_text": True, "role": "IDENTIFIER"},
        {"column": "Q11_7", "qid": "QID15", "choice": "8", "is_text": False, "role": "COMPARE"},
        {"column": "Q13", "qid": "QID42", "choice": "", "is_text": True, "role": "COMPARE"}]}
    header = pd.DataFrame({"column": ["QID2", "Q11_7", "Q13"], "question_text": ["Code", "Damage", "Details"],
                           "import_id": ["QID2_TEXT", "QID15_8", "QID42_TEXT"], "choice_id": ["", "", ""]})
    hs = pd.DataFrame({"survey_code": ["1-0001"], "ResponseId": ["R_a1"], "Q11_7": ["1"], "Q13": [""]}).set_index("survey_code")
    ch = pd.DataFrame({"survey_code": ["1-0001", "1-0009"], "ResponseId": ["R_b1", "R_b9"],
                       "Q11_7": ["5", "5"], "Q13": ["", ""]}).set_index("survey_code")
    make = lambda: Project(config=CONFIG, qmap=qmap, entries={"HS": hs, "CH": ch}, store=tmp_path, decisions={}, header=header)
    p = make()

    # A survey only Caleb typed can't be built from "HS": no silent all-blank record.
    with pytest.raises(ValueError, match="not entered by 'HS'"):
        p.record("1-0009", "HS")
    with pytest.raises(ValueError, match="not entered by 'HS'"):
        p.set_status("1-0009", "HS", "done")

    # Grid: only scale codes are valid.
    assert p.options("Q11_7") == ["", "1", "5"]
    with pytest.raises(ValueError, match="not a valid answer"):
        p.save("1-0001", "HS", {"Q11_7": "8", "Q13": ""})

    tricky = 'Café, "2nd" floor\nwater; 100%'
    p.save("1-0001", "HS", {"Q11_7": "5", "Q13": tricky})
    p.set_status("1-0001", "HS", "done")

    # Closing and reopening the tool: a fresh start reads the saved corrections.
    p = make()
    assert p.record("1-0001", "HS") == {"Q11_7": "5", "Q13": tricky}

    # Commas, quotes, line breaks and accents survive the CSV exactly; the grid row lands in its column.
    p.export(tmp_path / "out.csv")
    with open(tmp_path / "out.csv", newline="", encoding="utf-8") as f:
        assert list(csv.reader(f))[3] == ["1-0001", "5", tricky]

    # Editing a survey that was done puts it back to "in progress" (must be checked and marked done again).
    p.save("1-0001", "HS", {"Q11_7": "1", "Q13": tricky})
    assert p.surveys().set_index("survey_code").loc["1-0001", "status"] == "in progress"


def test_another_survey_set_up_only_in_the_config(tmp_path):
    """Nothing is tied to the ERC survey: other initials, another code format, its own decisions sheet."""
    pd.DataFrame({"Site": ["b", "b"], "No.": ["7", "8"], "Issue": ["Q1: two ticked", "Q13: unclear"],
                  "Decision": ["use the first", "leave"], "Why": ["", ""]}).to_excel(
        tmp_path / "team.xlsx", sheet_name="Decisions", index=False)
    config = replace(CONFIG, code_pattern=r"^[A-Z]-\d{3}$", code_example="B-012", decisions={
        "file": tmp_path / "team.xlsx", "sheet": "Decisions", "label": "Team", "survey_columns": ["Site", "No."],
        "question_column": "Issue", "decision_column": "Decision", "notes_column": "Why"})
    row = lambda code: {"survey_code": code, "ResponseId": "R", "Q1": "2", "Q9_1": "", "Q9_6_TEXT": "", "Q13": ""}
    entries = {n: pd.DataFrame([row("B-007")]).set_index("survey_code") for n in ("AA", "BB")}
    unsigned = pd.DataFrame([row("B-007-2") | {"source_file": "main.csv"},
                             row("B-007") | {"source_file": "bb_own.csv"}]).assign(entrant="", reason="NO_INITIALS")
    header = pd.DataFrame({"column": ["QID2", "Q1", "Q9_1", "Q9_6_TEXT", "Q13"], "question_text": [""] * 5,
                           "import_id": ["QID2_TEXT", "QID3", "QID12", "QID12_6_TEXT", "QID42_TEXT"], "choice_id": [""] * 5})
    p = Project(config=config, qmap=QMAP, entries=entries, store=tmp_path, header=header, excluded=unsigned)

    assert p.number("B-007-2") == "B-007"                               # same survey number, other paper
    assert list(p.starts["B-007"]) == ["AA", "BB", "no initials", "online (B-007-2)"]
    assert [d["tag"] for d in p.wj["B-007"]] == ["Q1"]                   # "b" + "7" is B-007, not B-008
    with pytest.raises(ValueError, match="e.g. B-012"):
        p.new_survey("1-0235")
    p.new_survey("B-009")
