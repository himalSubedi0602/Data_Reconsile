from recon.qsf import read_choices, read_questions

from conftest import FIXTURES

QSF = FIXTURES / "fake_survey.qsf"


def test_lists_questions_in_qid_order_without_text_blocks():
    q = read_questions(QSF)
    assert list(q["qid"]) == ["QID2", "QID3", "QID10", "QID15"]    # QID1 is display text
    assert list(q["type"]) == ["TE", "MC", "MC", "Matrix"]


def test_export_tag_falls_back_to_qid():
    q = read_questions(QSF).set_index("qid")
    assert q.loc["QID2", "export_tag"] == "QID2"
    assert q.loc["QID3", "export_tag"] == "Q1"


def test_question_text_is_plain():
    q = read_questions(QSF).set_index("qid")
    assert q.loc["QID10", "text"] == "Basement use? Check all"


def test_choice_codes_use_recode_values():
    c = read_choices(QSF)
    q1 = c[c["qid"] == "QID3"]
    assert list(zip(q1["code"], q1["label"])) == [("1", "Less than 1 year"), ("5", "21+ years")]


def test_other_choices_have_text_box():
    c = read_choices(QSF)
    assert list(c.loc[c["has_text"], ["qid", "code"]].itertuples(index=False, name=None)) == [
        ("QID10", "6"), ("QID15", "9")]


def test_grid_rows_and_scale():
    c = read_choices(QSF)
    grid = c[c["qid"] == "QID15"]
    assert list(zip(grid["kind"], grid["code"])) == [
        ("row", "1"), ("row", "9"), ("scale", "1"), ("scale", "5")]


def test_text_questions_have_no_choices():
    assert "QID2" not in set(read_choices(QSF)["qid"])
