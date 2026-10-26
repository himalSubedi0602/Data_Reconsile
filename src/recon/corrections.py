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

from recon.compare import _label, _plain, compare, same_text
from recon.config import load_config
from recon.loader import load, read_export

STATUSES = ("not started", "in progress", "done")
_CHANGES = ["time", "survey_code", "start", "column", "old", "new"]
_STATUS = ["time", "survey_code", "start", "status"]
_NEW_CODES = ["time", "new_code", "from_code"]


class Project:
    def __init__(self, config=None, qmap=None, entries=None, store=None, wj=None, header=None, excluded=None):
        """Load everything once. The keyword arguments let tests pass small fake data instead."""
        self.config = config or load_config()
        # The export's 3 header rows (name, question text, ImportId), used to lay out the CSV.
        self.header = header if header is not None else read_export(self.config.export_file)[0]
        self.qmap = qmap or json.loads((self.config.path.parent / "questions.json").read_text(encoding="utf-8"))
        if entries is None:
            result = load(self.config)
            names = {e.dataset: i for i, e in self.config.entrants.items()}       # "A" -> "HS"
            entries = {names[d]: df.set_index("survey_code") for d, df in result.datasets.items()}
            excluded = result.excluded
        # Every entry with its survey code, including the ones set aside (for the "Entries" box).
        used = [e.reset_index().assign(entrant=n, reason="") for n, e in entries.items()]
        self.all_entries = pd.concat(used + ([excluded] if excluded is not None else []), ignore_index=True)
        self.entries = entries                                                     # "HS"/"CH" -> table by code
        self.names = tuple(entries)
        # Every HS/CH entry a survey can be corrected from, used or set aside: code -> {start: row}.
        # The start is "HS", or "HS <recorded time>" when that person typed the code more than once.
        self.starts = {}
        for n in self.names:
            for code, g in self.all_entries[self.all_entries["entrant"] == n].groupby("survey_code"):
                for _, r in g.iterrows():
                    self.starts.setdefault(code, {})[n if len(g) == 1 else f"{n} {r['RecordedDate']}"] = r
        self.store = Path(store or self.config.working_dir.parent / "corrections")
        for row in self._rows(self.store / "new_codes.csv", _NEW_CODES):          # second papers, own code
            self.starts[row["new_code"]] = self.starts[row["from_code"]]
        self.columns = {c["column"]: c for c in self.qmap["columns"] if c["role"] == "COMPARE"}
        self.wj = wj if wj is not None else _read_wj(self.config.workbook_file)
        a, b = (entries[n].reset_index() for n in self.names)
        self.differences = compare(a, b, self.qmap, self.names).groupby("survey_code")["column"].apply(set)

    # ------------------------------------------------------------ what's on screen

    def surveys(self) -> pd.DataFrame:
        """One row per survey code entered by either person, used or set aside ("HS ×2 + CH" = typed more than once)."""
        status = self._latest(self.store / "status.csv", _STATUS)
        rows = []
        for code in sorted(self.starts):
            s = status.get(code, {})
            who = [start.split()[0] for start in self.starts[code]]
            rows.append({"survey_code": code,
                         "entered_by": " + ".join(n + (f" ×{who.count(n)}" if who.count(n) > 1 else "")
                                                  for n in self.names if n in who),
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

    def value(self, start: str, code: str, column: str) -> str:
        """One entry's original answer for one column ("" if there is no such entry)."""
        row = self.starts.get(code, {}).get(start)
        return "" if row is None else row[column]

    def label(self, column: str, value: str) -> str:
        c = self.columns[column]
        return _label(value, c, self.qmap["questions"][c["qid"]])

    def disagree(self, code: str, column: str) -> bool:
        return column in self.differences.get(code, ())

    def related_entries(self, code: str) -> pd.DataFrame:
        """Every entry with the same survey number (e.g. 1-0897 and 1-0897-1661), used or set aside."""
        base = _number(code)
        e = self.all_entries[self.all_entries["survey_code"].str.startswith(base)]
        who = e["entrant"].replace("", "no initials")
        if "source_file" in e:
            who = who.where(~((e["entrant"] == "") & ~e["source_file"].str.contains("_ch_")), "online participant")
        return pd.DataFrame({
            "Survey code": e["survey_code"], "Typed as": e.get("QID2", e["survey_code"]), "Entered by": who,
            "Recorded": e.get("RecordedDate", ""),
            "In the tool": e["reason"].map(lambda r: "used" if not r else ("no initials" if r == "NO_INITIALS" else _plain(r))),
        }).sort_values(["Survey code", "Entered by"]).reset_index(drop=True)

    def add_code(self, new_code: str, from_code: str):
        """Give another paper that shares from_code its own code (e.g. 3-2756-2). It is corrected from
        the same typed entries and exported under the new code."""
        new_code = new_code.strip()
        if new_code in self.starts:
            raise ValueError(f"{new_code} already exists")
        if _number(new_code) != _number(from_code) or new_code == _number(new_code):
            raise ValueError(f"{new_code} must be {_number(from_code)} with something added at the end, e.g. {from_code}-2")
        self._append(self.store / "new_codes.csv", _NEW_CODES,
                     [[datetime.now().isoformat(timespec="seconds"), new_code, from_code]])
        self.starts[new_code] = self.starts[from_code]

    def difference_notes(self, code: str) -> pd.DataFrame:
        """One row per question where the two entries disagree, with the kind of difference."""
        rows = []
        for q, cols in self.questions():
            for c in cols:
                col = c["column"]
                if not self.disagree(code, col):
                    continue
                a, b = (self.value(n, code, col) for n in self.names)
                nopunct = lambda s: " ".join(re.sub(r"[^\w\s]", " ", same_text(s)).split())
                if "" in (a, b):
                    kind = f"Left blank by {self.names[(a != '') * 1]}"
                elif c["is_text"]:
                    kind = "Only punctuation differs" if nopunct(a) == nopunct(b) else "Text written differently"
                elif q["kind"] == "grid":
                    kind = "Different rating"
                else:
                    kind = "Different answer"
                option = {**q.get("choices", {}), **q.get("rows", {})}.get(c["choice"], "")
                rows.append({"Question": q["tag"], "Option / row": option,
                             self.names[0]: self.label(col, a), self.names[1]: self.label(col, b), "Difference": kind})
        return pd.DataFrame(rows, columns=["Question", "Option / row", *self.names, "Difference"])

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
        self._check_start(code, start)
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
        self._check_start(code, start)
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

    def _check_start(self, code: str, start: str):
        """Refuse to build a record from an entry that doesn't exist (it would be all blank)."""
        if start not in self.starts.get(code, {}):
            raise ValueError(f"Survey {code} was not entered by {start!r}")

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


def _number(code: str) -> str:
    """The survey number part of a code: 1-0897-1661 -> 1-0897."""
    return m.group(1) if (m := re.match(r"(\d+-\d{4})(?!\d)", code)) else code


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
