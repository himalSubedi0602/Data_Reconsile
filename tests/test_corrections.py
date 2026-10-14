import csv

import pandas as pd
import pytest

from recon.corrections import Project
from test_compare import QMAP


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
    return Project(config=object(), qmap=qmap, entries=entries, store=tmp_path, wj={}, header=header)


def test_changes_land_in_the_right_place_and_nothing_else_changes(tmp_path):
    p = _project(tmp_path)
    assert p.disagree("1-0001", "Q1") and not p.disagree("1-0001", "Q13")
    assert p.surveys().set_index("survey_code").loc["1-0002", "entered_by"] == "HS"

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
