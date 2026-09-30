from recon.qsf import read_choices, read_questions

from conftest import FIXTURES

QSF = FIXTURES / "fake_survey.qsf"


def test_read_questions():
    q = read_questions(QSF)
    assert list(q["qid"]) == ["QID2", "QID3", "QID10", "QID15"]    # QID1 is display text, skipped
    assert list(q["type"]) == ["TE", "MC", "MC", "Matrix"]
    q = q.set_index("qid")
    assert q.loc["QID2", "export_tag"] == "QID2"                   # no tag -> named after the QID
    assert q.loc["QID10", "text"] == "Basement use? Check all"     # HTML removed


def test_read_choices():
    c = read_choices(QSF)
    rows = list(c[["qid", "kind", "code", "has_text"]].itertuples(index=False, name=None))
    assert rows == [
        ("QID10", "choice", "1", False), ("QID10", "choice", "6", True),   # Other box
        ("QID3", "choice", "1", False), ("QID3", "choice", "5", False),    # recoded 2 -> 5
        ("QID15", "row", "1", False), ("QID15", "row", "9", True),
        ("QID15", "scale", "1", False), ("QID15", "scale", "5", False),
    ]                                                                      # QID2 (text) has none
