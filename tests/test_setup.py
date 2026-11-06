import csv
import io
from pathlib import Path

import pytest

from recon import setup
from recon.config import load_config
from recon.corrections import Project

FIXTURES = Path(__file__).parent / "fixtures"
HEADER = [("StartDate", "Start Date", "startDate", ""), ("ResponseId", "Response ID", "_recordId", ""),
          ("RecordedDate", "Recorded Date", "recordedDate", ""), ("QID2", "Survey code", "QID2_TEXT", ""),
          ("Q1", "How long?", "QID3", ""), ("Q9_1", "Basement - Storage", "QID10", "1"),
          ("Q9_6", "Basement - Other", "QID10", "6"), ("Q9_6_TEXT", "Basement - Other - Text", "QID10_6_TEXT", ""),
          ("Q11_9", "How often? - Other", "QID15_9", ""), ("Q11_9_TEXT", "How often? - Other - Text", "QID15_9_TEXT", "")]


def _export(rows) -> bytes:
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow([h[0] for h in HEADER])
    w.writerow([h[1] for h in HEADER])
    w.writerow(['{"ImportId":"%s"%s}' % (i, f',"choiceId":"{c}"' if c else "") for _, _, i, c in HEADER])
    for n, (code, q1) in enumerate(rows):
        w.writerow(["2026-01-01", f"R_{n}", f"2026-01-0{n + 1}", code, q1, "1", "", "", "", ""])
    return out.getvalue().encode()


def test_a_new_survey_is_set_up_from_the_screen(tmp_path):
    qsf = ("survey.qsf", (FIXTURES / "fake_survey.qsf").read_bytes())
    main = ("responses.csv", _export([("B-07 AA", "1"), ("B-07 BB", "5"), ("B-08 AA", "1"), ("B-08", "5")]))
    with pytest.raises(ValueError, match="isn't a Qualtrics survey file"):
        setup.create("Test", ("survey.qsf", b"not a survey"), main, base=tmp_path)
    assert setup.projects(tmp_path) == []                               # nothing written for bad files

    root = setup.create("Test", qsf, main, base=tmp_path)
    with pytest.raises(ValueError, match="already a project"):
        setup.create("Test", qsf, main, base=tmp_path)
    assert not setup.is_ready(root)
    assert setup.code_questions(root)[0]["column"] == "QID2"            # the code question is suggested
    assert setup.initials(root, "QID2") == {"AA": 2, "BB": 1}
    assert setup.typical_code(setup.codes(root, "QID2")) == "B-07"
    summary = dict(setup.prepare(root, "QID2", ["AA", "BB"], "B-07"))
    assert summary["Surveys where AA and BB disagree"] == 1             # B-07: 1 vs 5

    assert setup.projects(tmp_path) == [root] and setup.is_ready(root)
    p = Project(config=load_config(root / "config/project.json"))       # opens like any project
    assert list(p.starts["B-08"]) == ["AA", "online"]
