import pandas as pd
import pytest

from recon.qsf import read_choices, read_questions
from recon.questions import build_question_map, link_columns, review_table

from conftest import FIXTURES


def test_link_columns():
    columns = pd.DataFrame({
        "column":    ["ResponseId", "QID2",      "Q2",   "Q2_4_TEXT",   "Q9_4",  "Q11_7"],
        "import_id": ["_recordId",  "QID2_TEXT", "QID4", "QID4_4_TEXT", "QID12", "QID15_8"],
        "choice_id": ["",           "",          "",     "",            "4",     ""],
    })
    linked = link_columns(columns).set_index("column")
    assert linked.loc["ResponseId", "qid"] == ""                       # metadata
    assert tuple(linked.loc["QID2", ["qid", "choice", "is_text"]]) == ("QID2", "", True)
    assert tuple(linked.loc["Q2", ["qid", "choice", "is_text"]]) == ("QID4", "", False)
    assert tuple(linked.loc["Q2_4_TEXT", ["qid", "choice", "is_text"]]) == ("QID4", "4", True)
    assert tuple(linked.loc["Q9_4", ["qid", "choice", "is_text"]]) == ("QID12", "4", False)
    # Grid column names don't follow the row IDs: Q11_7 is row 8.
    assert tuple(linked.loc["Q11_7", ["qid", "choice", "is_text"]]) == ("QID15", "8", False)


def test_build_question_map_and_review_table():
    qsf = FIXTURES / "fake_survey.qsf"
    columns = pd.DataFrame({
        "column":    ["StartDate", "QID2",      "Q1",   "Q9_1",  "Q9_6",  "Q9_6_TEXT",    "Q11_9",   "Q11_9_TEXT"],
        "import_id": ["startDate", "QID2_TEXT", "QID3", "QID10", "QID10", "QID10_6_TEXT", "QID15_9", "QID15_9_TEXT"],
        "choice_id": ["",          "",          "",     "1",     "6",     "",             "",        ""],
    })
    qmap = build_question_map(columns, read_questions(qsf), read_choices(qsf), "QID2")
    q = qmap["questions"]
    assert {k: v["kind"] for k, v in q.items()} == {
        "QID2": "text", "QID3": "single_choice", "QID10": "check_all", "QID15": "grid"}
    assert q["QID3"]["choices"] == {"1": "Less than 1 year", "5": "21+ years"}
    assert q["QID15"]["rows"] == {"1": "Nuisance flooding", "9": "Other, please describe:"}
    assert q["QID15"]["scale"] == {"1": "Always", "5": "Never"}

    review = review_table(qmap).set_index("column")
    assert review.loc["Q9_1", "option"] == "Storage"
    assert review.loc["Q11_9_TEXT", "option"] == "Other, please describe:"
    assert review.loc["StartDate", "role"] == "METADATA"


def test_build_question_map_stops_when_columns_and_qsf_dont_line_up():
    qsf = FIXTURES / "fake_survey.qsf"
    columns = pd.DataFrame({
        "column":    ["QID2",      "Q1",   "Q1_copy", "Q9_3",  "Q99"],
        "import_id": ["QID2_TEXT", "QID3", "QID3",    "QID10", "QID99"],
        "choice_id": ["",          "",     "",        "3",     ""],
    })
    with pytest.raises(ValueError) as e:
        build_question_map(columns, read_questions(qsf), read_choices(qsf), "QID2")
    message = str(e.value)
    assert "Q99: question QID99 is not in the .qsf" in message
    assert "QID15 (Q11): has no column in the export" in message
    assert "Q9_3: option 3 is not an option of QID10" in message
    assert "Q1_copy: another column holds the same answer" in message
