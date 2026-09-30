"""Build the question map (questions.json): what each export column means.

Run from the project root:  python -m recon.questions
"""

import json

import pandas as pd

from recon.config import load_config
from recon.loader import read_export
from recon.qsf import read_choices, read_questions

# (.qsf question type, selector) -> how its answers are compared
KINDS = {("MC", "SAVR"): "single_choice", ("MC", "MAVR"): "check_all",
         ("Matrix", "Likert"): "grid", ("TE", "ML"): "text"}

# ImportId forms: QID4 (answer), QID15_8 (grid row 8), QID4_4_TEXT (text box of choice 4),
# QID2_TEXT (text question). Check-all options carry their choice in choice_id instead.
IMPORT_ID = r"^(QID\d+)(?:_(\d+))?(_TEXT)?$"


def link_columns(columns: pd.DataFrame) -> pd.DataFrame:
    """Add qid, choice and is_text to the export's column list. Metadata columns get qid ''."""
    parts = columns["import_id"].str.extract(IMPORT_ID).fillna("")
    out = columns.copy()
    out["qid"] = parts[0]
    out["choice"] = parts[1].where(parts[1] != "", columns["choice_id"])
    out["is_text"] = parts[2] != ""
    return out


def assign_roles(linked: pd.DataFrame, id_column: str) -> pd.DataFrame:
    """Add role: METADATA (Qualtrics' own columns, never compared), IDENTIFIER (the survey
    code, used to match A with B) or COMPARE (an answer)."""
    out = linked.copy()
    out["role"] = "COMPARE"
    out.loc[out["qid"] == "", "role"] = "METADATA"
    out.loc[out["column"] == id_column, "role"] = "IDENTIFIER"
    return out


def other_pairs(linked: pd.DataFrame) -> pd.DataFrame:
    """Each "Other" text-box column, with the column that says whether Other was picked.

    other_code: the code in select_column that means Other (pick-one questions).
    Blank means select_column is the option's own column (a tick-box or grid row).
    """
    answers = linked[~linked["is_text"] & (linked["qid"] != "")]
    rows = []
    for t in linked[linked["is_text"] & (linked["choice"] != "")].itertuples():
        own = answers[(answers["qid"] == t.qid) & (answers["choice"] == t.choice)]
        if len(own):
            rows.append((t.column, own["column"].iloc[0], ""))
        else:
            rows.append((t.column, answers.loc[answers["qid"] == t.qid, "column"].iloc[0], t.choice))
    return pd.DataFrame(rows, columns=["text_column", "select_column", "other_code"])


def build_question_map(columns, questions, choices, id_column) -> dict:
    """Everything later steps need to know about the columns, as one JSON-ready dict."""
    linked = assign_roles(link_columns(columns), id_column)
    qmap = {}
    for q in questions.itertuples():
        if (q.type, q.selector) not in KINDS:
            raise ValueError(f"{q.qid} ({q.export_tag}): unsupported question type {q.type}/{q.selector}")
        entry = {"tag": q.export_tag, "kind": KINDS[q.type, q.selector], "text": q.text}
        for kind, key in (("choice", "choices"), ("row", "rows"), ("scale", "scale")):
            options = choices[(choices["qid"] == q.qid) & (choices["kind"] == kind)]
            if len(options):
                entry[key] = dict(zip(options["code"], options["label"]))
        qmap[q.qid] = entry
    return {
        "columns": linked[["column", "qid", "choice", "is_text", "role"]].to_dict("records"),
        "questions": qmap,
        "other_pairs": other_pairs(linked).to_dict("records"),
    }


def review_table(qmap: dict) -> pd.DataFrame:
    """One readable row per column, for a person to check the map."""
    rows = []
    for c in qmap["columns"]:
        q = qmap["questions"].get(c["qid"], {})
        options = {**q.get("choices", {}), **q.get("rows", {})}
        rows.append({"column": c["column"], "role": c["role"], "question": q.get("tag", ""),
                     "kind": q.get("kind", ""), "option": options.get(c["choice"], ""),
                     "text_box": c["is_text"], "question_text": q.get("text", "")})
    return pd.DataFrame(rows)


def main():
    config = load_config()
    qmap = build_question_map(read_export(config.export_file)[0], read_questions(config.qsf_file),
                              read_choices(config.qsf_file), config.id_column)
    out = config.path.parent / "questions.json"
    out.write_text(json.dumps(qmap, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    review = config.working_dir / "questions_review.csv"
    review_table(qmap).to_csv(review, index=False, encoding="utf-8-sig")
    print(f"Wrote {out} ({len(qmap['questions'])} questions, {len(qmap['columns'])} columns, "
          f"{len(qmap['other_pairs'])} Other pairs) and {review}")


if __name__ == "__main__":
    main()
