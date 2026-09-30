import pandas as pd

from recon.qsf import read_choices, read_questions
from recon.questions import (
    assign_roles, build_question_map, link_columns, other_pairs, review_table,
)

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


def test_other_pairs():
    linked = link_columns(pd.DataFrame({
        "column":    ["QID2",      "Q2",   "Q2_4_TEXT",   "Q9_6",  "Q9_6_TEXT",    "Q11_9",   "Q11_9_TEXT"],
        "import_id": ["QID2_TEXT", "QID4", "QID4_4_TEXT", "QID12", "QID12_6_TEXT", "QID15_9", "QID15_9_TEXT"],
        "choice_id": ["",          "",     "",            "6",     "",             "",        ""],
    }))
    pairs = other_pairs(linked)
    assert list(pairs.itertuples(index=False, name=None)) == [
        ("Q2_4_TEXT", "Q2", "4"),        # pick-one: Other picked when Q2 == 4
        ("Q9_6_TEXT", "Q9_6", ""),       # tick-box: the option's own column
        ("Q11_9_TEXT", "Q11_9", ""),     # grid: the "Other" row's rating
    ]                                    # QID2 is a text question, not an Other box


def test_assign_roles():
    linked = link_columns(pd.DataFrame({
        "column":    ["StartDate", "QID2",      "Q2"],
        "import_id": ["startDate", "QID2_TEXT", "QID4"],
        "choice_id": ["",          "",          ""],
    }))
    assert list(assign_roles(linked, "QID2")["role"]) == ["METADATA", "IDENTIFIER", "COMPARE"]


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
    assert len(qmap["other_pairs"]) == 2

    review = review_table(qmap).set_index("column")
    assert review.loc["Q9_1", "option"] == "Storage"
    assert review.loc["Q11_9_TEXT", "option"] == "Other, please describe:"
    assert review.loc["StartDate", "role"] == "METADATA"
