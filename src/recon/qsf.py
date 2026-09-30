"""Read question definitions from a Qualtrics .qsf survey file."""

import html
import json
import re
from pathlib import Path

import pandas as pd


def _plain(text: str) -> str:
    """Question text without HTML tags, entities or extra spacing."""
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", text)).split())


def _questions(path) -> list[dict]:
    """Raw question definitions, without display-only text blocks."""
    survey = json.loads(Path(path).read_text(encoding="utf-8"))
    return [e["Payload"] for e in survey["SurveyElements"]
            if e["Element"] == "SQ" and e["Payload"]["QuestionType"] != "DB"]


def read_questions(path) -> pd.DataFrame:
    """One row per question, in QID order."""
    rows = [{
        "qid": q["QuestionID"],
        # Qualtrics names the export column after the QID when no tag is set.
        "export_tag": q.get("DataExportTag") or q["QuestionID"],
        "type": q["QuestionType"],
        "selector": q.get("Selector", ""),
        "text": _plain(q.get("QuestionText", "")),
    } for q in _questions(path)]
    return (pd.DataFrame(rows)
            .sort_values("qid", key=lambda s: s.str[3:].astype(int))
            .reset_index(drop=True))


def read_choices(path) -> pd.DataFrame:
    """One row per answer option, with the code the export uses for it.

    kind: "choice" (multiple choice), or for grids "row" (a statement) and "scale" (an answer).
    has_text: the option has its own text box (e.g. "Other, please describe").
    """
    rows = []
    for q in _questions(path):
        recode = q.get("RecodeValues") or {}   # export uses these codes when set
        grid = q["QuestionType"] == "Matrix"
        for cid, c in (q.get("Choices") or {}).items():
            rows.append({"qid": q["QuestionID"], "kind": "row" if grid else "choice",
                         "code": cid if grid else recode.get(cid, cid),
                         "label": _plain(c["Display"]), "has_text": "TextEntry" in c})
        for aid, a in (q.get("Answers") or {}).items():
            rows.append({"qid": q["QuestionID"], "kind": "scale", "code": recode.get(aid, aid),
                         "label": _plain(a["Display"]), "has_text": False})
    return pd.DataFrame(rows, columns=["qid", "kind", "code", "label", "has_text"])
