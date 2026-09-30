from recon.qsf import read_questions

from conftest import FIXTURES


def test_lists_questions_in_qid_order_without_text_blocks():
    q = read_questions(FIXTURES / "fake_survey.qsf")
    assert list(q["qid"]) == ["QID2", "QID3", "QID10"]          # QID1 is display text
    assert list(q["type"]) == ["TE", "MC", "MC"]
    assert list(q["selector"]) == ["ML", "SAVR", "MAVR"]


def test_export_tag_falls_back_to_qid():
    q = read_questions(FIXTURES / "fake_survey.qsf").set_index("qid")
    assert q.loc["QID2", "export_tag"] == "QID2"
    assert q.loc["QID3", "export_tag"] == "Q1"


def test_question_text_is_plain():
    q = read_questions(FIXTURES / "fake_survey.qsf").set_index("qid")
    assert q.loc["QID10", "text"] == "Basement use? Check all"
