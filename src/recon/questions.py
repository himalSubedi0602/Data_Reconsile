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
    problems = _coverage_problems(linked, qmap)
    if problems:
        raise ValueError("Export columns and .qsf don't line up:\n  " + "\n  ".join(problems))
    return {
        "columns": linked[["column", "qid", "choice", "is_text", "role"]].to_dict("records"),
        "questions": qmap,
    }


def _coverage_problems(linked: pd.DataFrame, qmap: dict) -> list[str]:
    """Each answer column must be exactly one known part of a known question,
    and each question must have at least one column."""
    answers = linked[linked["qid"] != ""]
    problems = [f"{c}: question {q} is not in the .qsf"
                for c, q in zip(answers["column"], answers["qid"]) if q not in qmap]
    problems += [f"{q} ({e['tag']}): has no column in the export"
                 for q, e in qmap.items() if q not in set(answers["qid"])]
    for c in answers[answers["choice"] != ""].itertuples():
        q = qmap.get(c.qid, {})
        if c.choice not in {**q.get("choices", {}), **q.get("rows", {})}:
            problems.append(f"{c.column}: option {c.choice} is not an option of {c.qid}")
    repeated = answers[answers.duplicated(["qid", "choice", "is_text"], keep=False)]
    problems += [f"{c}: another column holds the same answer" for c in repeated["column"]]
    return problems


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
    print(f"Wrote {out} ({len(qmap['questions'])} questions, {len(qmap['columns'])} columns) "
          f"and {review}")


if __name__ == "__main__":
    main()
