"""Read question definitions from a Qualtrics .qsf survey file."""

import html
import json
import re
from pathlib import Path

import pandas as pd


def _plain(text: str) -> str:
    """Question text without HTML tags, entities or extra spacing."""
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", text)).split())


def read_questions(path) -> pd.DataFrame:
    """One row per question, in QID order. Display-only text blocks are skipped."""
    survey = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = []
    for element in survey["SurveyElements"]:
        q = element["Payload"]
        if element["Element"] != "SQ" or q["QuestionType"] == "DB":
            continue
        rows.append({
            "qid": q["QuestionID"],
            # Qualtrics names the export column after the QID when no tag is set.
            "export_tag": q.get("DataExportTag") or q["QuestionID"],
            "type": q["QuestionType"],
            "selector": q.get("Selector", ""),
            "text": _plain(q.get("QuestionText", "")),
        })
    return (pd.DataFrame(rows)
            .sort_values("qid", key=lambda s: s.str[3:].astype(int))
            .reset_index(drop=True))
