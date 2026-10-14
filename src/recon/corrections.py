"""Logic behind the correction tool: surveys, both entries, W&J hints, saved changes.

Nothing here changes the raw data. A corrected survey is always rebuilt as:
the entry chosen as the starting point + the changes saved in data/corrections/.
"""

import csv
import json
import random
import re
from datetime import datetime
from pathlib import Path

import pandas as pd

from recon.compare import _label, compare
from recon.config import load_config
from recon.loader import load, read_export

STATUSES = ("not started", "in progress", "done")
_CHANGES = ["time", "survey_code", "start", "column", "old", "new"]
_STATUS = ["time", "survey_code", "start", "status"]


class Project:
    def __init__(self, config=None, qmap=None, entries=None, store=None, wj=None, header=None):
        """Load everything once. The keyword arguments let tests pass small fake data instead."""
        self.config = config or load_config()
        # The export's 3 header rows (name, question text, ImportId), used to lay out the CSV.
        self.header = header if header is not None else read_export(self.config.export_file)[0]
        self.qmap = qmap or json.loads((self.config.path.parent / "questions.json").read_text(encoding="utf-8"))
        if entries is None:
            datasets = load(self.config).datasets
            names = {e.dataset: i for i, e in self.config.entrants.items()}       # "A" -> "HS"
            entries = {names[d]: df.set_index("survey_code") for d, df in datasets.items()}
        self.entries = entries                                                     # "HS"/"CH" -> table by code
        self.names = tuple(entries)
        self.store = Path(store or self.config.working_dir.parent / "corrections")
        self.columns = {c["column"]: c for c in self.qmap["columns"] if c["role"] == "COMPARE"}
        self.wj = wj if wj is not None else _read_wj(self.config.workbook_file)
        a, b = (entries[n].reset_index() for n in self.names)
        self.differences = compare(a, b, self.qmap, self.names).groupby("survey_code")["column"].apply(set)

    # ------------------------------------------------------------ what's on screen

    def surveys(self) -> pd.DataFrame:
        """One row per survey code entered by either person."""
        codes = sorted(set().union(*(e.index for e in self.entries.values())))
        status = self._latest(self.store / "status.csv", _STATUS)
        rows = []
        for code in codes:
            s = status.get(code, {})
            rows.append({"survey_code": code,
                         "entered_by": " + ".join(n for n in self.names if code in self.entries[n].index),
                         "differences": len(self.differences.get(code, ())),
                         "wj": len(self.wj.get(code, ())),
                         "start": s.get("start", ""), "status": s.get("status", "not started")})
        return pd.DataFrame(rows)

    def questions(self) -> list[tuple[dict, list[dict]]]:
        """Questions in paper order, each with its columns in export order."""
        groups = {}
        for c in self.columns.values():
            groups.setdefault(c["qid"], []).append(c)
        return [(self.qmap["questions"][qid], cols) for qid, cols in groups.items()]

    def value(self, name: str, code: str, column: str) -> str:
        """One person's original entry for one column ("" if they didn't enter this survey)."""
        e = self.entries[name]
        return e.at[code, column] if code in e.index else ""

    def label(self, column: str, value: str) -> str:
        c = self.columns[column]
        return _label(value, c, self.qmap["questions"][c["qid"]])

    def disagree(self, code: str, column: str) -> bool:
        return column in self.differences.get(code, ())

    def options(self, column: str) -> list[str]:
        """Valid codes for a choice column, blank first ([] for text columns)."""
        c = self.columns[column]
        q = self.qmap["questions"][c["qid"]]
        if c["is_text"]:
            return []
        if q["kind"] == "check_all":
            return ["", "1"]
        return [""] + list(q.get("scale" if q["kind"] == "grid" else "choices", {}))

    # ------------------------------------------------------------ the corrected record

    def record(self, code: str, start: str) -> dict:
        """The corrected answers: the starting entry plus the saved changes (latest per column)."""
        values = {col: self.value(start, code, col) for col in self.columns}
        for row in self._rows(self.store / "changes.csv", _CHANGES):
            if row["survey_code"] == code and row["start"] == start:
                values[row["column"]] = row["new"]
        return values

    def save(self, code: str, start: str, new: dict, status: str = "in progress") -> int:
        """Log every answer that differs from the current record. Returns how many were saved."""
        current = self.record(code, start)
        changed = {col: v for col, v in new.items() if v != current[col]}
        for col, v in changed.items():
            if self.options(col) and v not in self.options(col):
                raise ValueError(f"{code} {col}: {v!r} is not a valid answer")
        now = datetime.now().isoformat(timespec="seconds")
        self._append(self.store / "changes.csv", _CHANGES,
                     [[now, code, start, col, current[col], v] for col, v in changed.items()])
        self.set_status(code, start, status)
        return len(changed)

    def set_status(self, code: str, start: str, status: str):
        assert status in STATUSES
        now = datetime.now().isoformat(timespec="seconds")
        self._append(self.store / "status.csv", _STATUS, [[now, code, start, status]])

    # ------------------------------------------------------------ results

    def export(self, path) -> int:
        """Write one row per survey marked done: the corrected answers as numeric codes, laid out
        like the Qualtrics export (3 header rows). The survey code is written without initials.
        Returns the number of surveys written."""
        id_col = next(c["column"] for c in self.qmap["columns"] if c["role"] == "IDENTIFIER")
        h = self.header[self.header["column"].isin([id_col, *self.columns])]
        ids = [json.dumps({"ImportId": i, **({"choiceId": c} if c else {})}, separators=(",", ":"))
               for i, c in zip(h["import_id"], h["choice_id"])]
        done = self.surveys().query("status == 'done'")
        rows = [[code if col == id_col else self.record(code, start)[col] for col in h["column"]]
                for code, start in zip(done["survey_code"], done["start"])]
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerows([list(h["column"]), list(h["question_text"]), ids, *rows])
        return len(rows)

    def random_check(self, path, n=10, seed=None) -> list[str]:
        """Validation 2: pick n surveys marked done at random and write their corrected answers in
        words, one row per question part, with a column to tick against the paper."""
        seed = seed if seed is not None else int(datetime.now().strftime("%Y%m%d%H%M%S"))
        done = self.surveys().query("status == 'done'")
        picked = sorted(random.Random(seed).sample(list(done["survey_code"]), min(n, len(done))))
        start = dict(zip(done["survey_code"], done["start"]))
        rows = []
        for code in picked:
            values = self.record(code, start[code])
            for q, cols in self.questions():
                for c in cols:
                    v = values[c["column"]]
                    if q["kind"] == "check_all" and not c["is_text"] and v == "":
                        continue                                           # unticked boxes left out
                    option = {**q.get("choices", {}), **q.get("rows", {})}.get(c["choice"], "")
                    rows.append({"Survey code": code, "Question": f"{q['tag']}. {q['text']}",
                                 "Option / row": option, "Answer": self.label(c["column"], v),
                                 "Matches paper? (Y/N)": "", "Notes": ""})
            rows.append({})
        with pd.ExcelWriter(path) as xl:
            pd.DataFrame([{"Random check": f"{len(picked)} surveys picked at random (seed {seed})",
                           "Surveys": ", ".join(picked)}]).to_excel(xl, sheet_name="About", index=False)
            pd.DataFrame(rows).to_excel(xl, sheet_name="Check", index=False)
            ws = xl.sheets["Check"]
            for col, w in zip("ABCDEF", [12, 60, 40, 40, 14, 30]):
                ws.column_dimensions[col].width = w
            ws.freeze_panes = "A2"
        return picked

    # ------------------------------------------------------------ storage (append-only CSVs)

    def _append(self, path: Path, header: list[str], rows: list[list]):
        if not rows:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        new = not path.exists()
        with open(path, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if new:
                w.writerow(header)
            w.writerows(rows)

    def _rows(self, path: Path, header: list[str]) -> list[dict]:
        if not path.exists():
            return []
        with open(path, newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))

    def _latest(self, path: Path, header: list[str]) -> dict:
        latest = {}
        for row in self._rows(path, header):
            latest[row["survey_code"]] = row
        return latest


def _read_wj(path) -> dict:
    """W&J decisions by survey code: [{"tag": "Q27" or "", "question", "rule", "notes"}]."""
    if not path or not Path(path).exists():
        return {}
    w = pd.read_excel(path, sheet_name="W&J", dtype=str).fillna("")
    out = {}
    for _, r in w.iterrows():
        loc, num = r.iloc[0].strip().split(".")[0], re.match(r"\s*(\d+)", r.iloc[1])
        if not loc or not num:
            continue
        tag = re.match(r"\s*Q\.?\s*(\d+)", r.iloc[2])
        out.setdefault(f"{loc}-{int(num.group(1)):04d}", []).append({
            "tag": f"Q{tag.group(1)}" if tag else "", "question": r.iloc[2].strip(),
            "rule": r.iloc[3].strip(), "notes": r.iloc[4].strip()})
    return out
