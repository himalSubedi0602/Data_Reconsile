import pandas as pd

from recon.compare import compare, survey_table

QMAP = {
    "questions": {
        "QID3": {"tag": "Q1", "kind": "single_choice", "text": "How long?",
                 "choices": {"2": "1-5 years", "3": "6-10 years"}},
        "QID12": {"tag": "Q9", "kind": "check_all", "text": "Basement use?",
                  "choices": {"1": "Storage", "6": "Other"}},
        "QID42": {"tag": "Q13", "kind": "text", "text": "Details"},
    },
    "columns": [
        {"column": "StartDate", "qid": "", "choice": "", "is_text": False, "role": "METADATA"},
        {"column": "Q1", "qid": "QID3", "choice": "", "is_text": False, "role": "COMPARE"},
        {"column": "Q9_1", "qid": "QID12", "choice": "1", "is_text": False, "role": "COMPARE"},
        {"column": "Q9_6_TEXT", "qid": "QID12", "choice": "6", "is_text": True, "role": "COMPARE"},
        {"column": "Q13", "qid": "QID42", "choice": "", "is_text": True, "role": "COMPARE"},
    ],
}
COLUMNS = ["survey_code", "ResponseId", "StartDate", "Q1", "Q9_1", "Q9_6_TEXT", "Q13"]


def test_compare_lists_real_disagreements_only():
    a = pd.DataFrame([
        ["1-0001", "R_a1", "9:00", "2", "1", " Garage ",          "Water in\nbasement"],
        ["1-0002", "R_a2", "9:00", "2", "",  "shed",               "ok"],
        ["1-0003", "R_a3", "9:00", "2", "1", "",                   ""],     # only in A
    ], columns=COLUMNS)
    b = pd.DataFrame([
        ["1-0001", "R_b1", "10:00", "2", "1", "garage",            "water in  basement"],  # same answers
        ["1-0002", "R_b2", "10:00", "3", "1", "shed.",             ""],
        ["1-0004", "R_b4", "10:00", "2", "1", "",                  ""],     # only in B
    ], columns=COLUMNS)
    differences = compare(a, b, QMAP, ("HS", "CH"))

    # 1-0001 differs only in spacing, capitals, line breaks and StartDate (metadata): not listed.
    assert list(zip(differences["survey_code"], differences["column"])) == [
        ("1-0002", "Q1"), ("1-0002", "Q9_1"), ("1-0002", "Q9_6_TEXT"), ("1-0002", "Q13")]
    rows = differences.set_index("column")
    assert tuple(rows.loc["Q1", ["HS answer", "CH answer"]]) == ("2 = 1-5 years", "3 = 6-10 years")
    assert tuple(rows.loc["Q9_1", ["HS answer", "CH answer"]]) == ("(blank)", "ticked")
    assert tuple(rows.loc["Q9_6_TEXT", ["HS answer", "CH answer"]]) == ("shed", "shed.")  # punctuation counts
    assert tuple(rows.loc["Q13", ["HS answer", "CH answer"]]) == ("ok", "(blank)")
    assert rows.loc["Q9_6_TEXT", "question"] == "Q9: Basement use? | Other"
    assert tuple(rows.loc["Q1", ["HS ResponseId", "CH ResponseId"]]) == ("R_a2", "R_b2")

    excluded = pd.DataFrame({"survey_code": ["1-0004", "1-0005"], "entrant": ["HS", "CH"],
                             "reason": ["NOT_ON_PAPER_LOG", "REPEATED_IN_EXPORT(2x)"]})
    surveys = survey_table(a, b, excluded, differences, ("HS", "CH")).set_index("survey_code")
    assert dict(surveys["status"]) == {
        "1-0001": "Compared: all answers match",
        "1-0002": "Compared: 4 differences",
        "1-0003": "Not compared: HS typed, CH not typed",
        "1-0004": "Not compared: HS set aside (not in paper log), CH typed",
        "1-0005": "Not compared: HS not typed, CH set aside (typed more than once)",
    }
    assert surveys.loc["1-0002", "columns that differ"] == "Q1, Q9_1, Q9_6_TEXT, Q13"
