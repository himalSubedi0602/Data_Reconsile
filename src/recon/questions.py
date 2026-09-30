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
