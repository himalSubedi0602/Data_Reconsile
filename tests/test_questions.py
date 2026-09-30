import pandas as pd

from recon.questions import link_columns


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
