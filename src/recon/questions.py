"""Build the question map (questions.json): what each export column means."""

import pandas as pd

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
