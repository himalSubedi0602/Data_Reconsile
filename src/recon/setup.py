"""Set up a survey project from the screen: upload the files, choose the settings, prepare it.

Each project is a folder laid out like this one, so the rest of the code works unchanged:
    projects/<name>/config/project.json      settings (written by the setup screen)
    projects/<name>/config/questions.json    what every column means (written by "Prepare")
    projects/<name>/data/raw/                the uploaded files, never changed
    projects/<name>/data/corrections/        saved corrections
The ERC project in this folder itself (config/project.json) is listed first.
"""

import csv
import json
import re
import tempfile
from collections import Counter
from pathlib import Path

from recon.compare import _plain
from recon.config import load_config
from recon.corrections import Project
from recon.loader import CODE_AND_INITIALS, LoaderError, load, parse_survey_code, read_export
from recon.qsf import read_choices, read_questions
from recon.questions import build_question_map

ROOT = Path(__file__).resolve().parents[2]
PROJECTS = ROOT / "projects"


def projects(base=PROJECTS) -> list[Path]:
    """Every project folder: this one first (if set up), then projects/ by name."""
    here = [ROOT] if (ROOT / "config/project.json").exists() and base == PROJECTS else []
    return here + sorted(p for p in Path(base).glob("*") if (p / "config/project.json").exists())


def is_ready(root: Path) -> bool:
    """Prepared: the settings are complete and the questions were read."""
    return (root / "config/questions.json").exists()


def draft(root: Path) -> dict:
    return json.loads((root / "config/project.json").read_text(encoding="utf-8"))


def done_count(root: Path) -> int:
    """Surveys marked done, from the saved status log (quick: no data loaded)."""
    path = root / "data/corrections/status.csv"
    if not path.exists():
        return 0
    with open(path, newline="", encoding="utf-8") as f:
        latest = {r["survey_code"]: r["status"] for r in csv.DictReader(f)}
    return sum(s == "done" for s in latest.values())


def create(name: str, qsf: tuple[str, bytes], main: tuple[str, bytes], extras=(), base=PROJECTS) -> Path:
    """New project folder with the uploaded files. Each upload is (file name, contents).
    The files are checked first: nothing is written if one isn't a Qualtrics survey or export."""
    name = name.strip()
    folder = re.sub(r"[^\w\- ]", "", name).strip()
    if not folder:
        raise ValueError("Give the project a name.")
    root = Path(base) / folder
    if root.exists():
        raise ValueError(f"There is already a project called {folder!r}.")
    files = [qsf, main, *extras]
    if len({n for n, _ in files}) < len(files):
        raise ValueError("Two of the uploaded files have the same name.")
    with tempfile.TemporaryDirectory() as tmp:
        for n, data in files:
            (Path(tmp) / n).write_bytes(data)
        try:
            read_questions(Path(tmp) / qsf[0])
        except Exception:
            raise ValueError(f"{qsf[0]} isn't a Qualtrics survey file (.qsf). In Qualtrics: "
                             "Tools → Import/Export → Export Survey.") from None
        first = None
        for n, _ in [main, *extras]:
            try:
                columns = read_export(Path(tmp) / n)[0]
            except LoaderError as e:
                raise ValueError(str(e)) from None
            if first is not None and list(columns["column"]) != list(first["column"]):
                raise ValueError(f"{n} has different columns from {main[0]}: is it the same survey?")
            first = columns
    (root / "config").mkdir(parents=True)
    (root / "data/raw").mkdir(parents=True)
    for n, data in files:
        (root / "data/raw" / n).write_bytes(data)
    settings = {"survey_name": name, "export_file": f"data/raw/{main[0]}",
                "extra_export_files": [f"data/raw/{n}" for n, _ in extras],
                "qsf_file": f"data/raw/{qsf[0]}", "raw_dir": "data/raw", "working_dir": "data/working"}
    (root / "config/project.json").write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    return root


def _exports(root: Path):
    d = draft(root)
    return [read_export(root / f)[1] for f in [d["export_file"], *d["extra_export_files"]]]


def code_questions(root: Path) -> list[dict]:
    """Text questions that could hold the survey code, the likeliest first: the share of answers
    that look like a code followed by initials ("1-0235 HS")."""
    columns, data = read_export(root / draft(root)["export_file"])
    out = []
    for c in columns[columns["import_id"].str.match(r"QID\d+_TEXT$")].itertuples():
        values = [v for v in data[c.column] if v.strip()]
        looks = sum(bool(CODE_AND_INITIALS.match("".join(v.split()))) for v in values)
        out.append({"column": c.column, "text": c.question_text, "example": values[0] if values else "",
                    "score": looks / len(values) if values else 0})
    return sorted(out, key=lambda q: -q["score"])


def initials(root: Path, id_column: str) -> Counter:
    """Initials found at the end of the codes, with how many entries each."""
    return Counter(i for d in _exports(root) for _, i in d[id_column].map(parse_survey_code) if i)


def codes(root: Path, id_column: str) -> list[str]:
    """Every typed code, initials removed."""
    return [c for d in _exports(root) for c, _ in d[id_column].map(parse_survey_code) if c]


def pattern_from_example(example: str) -> str:
    """'1-0235' -> '^\\d{1}-\\d{4}$': the same digits, letters and symbols in the same places."""
    parts = re.findall(r"\d+|[A-Za-z]+|.", example.strip())
    return "^" + "".join(rf"\d{{{len(p)}}}" if p.isdigit() else rf"[A-Za-z]{{{len(p)}}}" if p.isalpha()
                         else re.escape(p) for p in parts) + "$"


def typical_code(all_codes: list[str]) -> str:
    """A code in the most common format, as the suggested example."""
    shapes = Counter(pattern_from_example(c) for c in all_codes)
    best = shapes.most_common(1)[0][0] if shapes else ""
    return next((c for c in all_codes if pattern_from_example(c) == best), "")


def prepare(root: Path, id_column: str, people: list[str], example: str,
            paper_logs: dict | None = None, decisions: dict | None = None) -> list[tuple[str, object]]:
    """Save the settings, load the responses and read the questions. Returns a summary to show.
    paper_logs: person -> (file name, contents). decisions: the decisions settings plus "upload":
    (file name, contents). Raises ValueError with a plain message if something doesn't fit."""
    if len(set(people)) != 2:
        raise ValueError("Pick the two people who typed the surveys in.")
    if not example.strip():
        raise ValueError("Type one correct survey code.")
    raw = root / "data/raw"
    settings = draft(root)
    settings |= {"id_column": id_column, "code_pattern": pattern_from_example(example),
                 "code_example": example.strip(), "entrants": {}}
    for person, dataset in zip(people, "AB"):
        name, data = (paper_logs or {}).get(person) or (None, None)
        if name:
            (raw / name).write_bytes(data)
        settings["entrants"][person] = {"dataset": dataset, "paper_log": f"data/raw/{name}" if name else None}
    settings.pop("decisions", None)
    if decisions:
        name, data = decisions.pop("upload")
        (raw / name).write_bytes(data)
        settings["decisions"] = {**decisions, "file": f"data/raw/{name}"}
    (root / "config/project.json").write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")

    config = load_config(root / "config/project.json")
    try:
        result = load(config)
        qmap = build_question_map(result.columns, read_questions(config.qsf_file),
                                  read_choices(config.qsf_file), config.id_column)
        p = Project(config=config, qmap=qmap)
    except (LoaderError, ValueError, KeyError) as e:
        raise ValueError(f"The project couldn't be prepared: {e}") from None
    (root / "config/questions.json").write_text(json.dumps(qmap, indent=2, ensure_ascii=False) + "\n",
                                                encoding="utf-8")

    a, b = people
    c = result.record["counts"]
    surveys = p.surveys()
    summary = [("Responses read", c["entries_in_export"]),
               (f"Entries by {a} used for comparing", c["dataset_A"]),
               (f"Entries by {b} used for comparing", c["dataset_B"]),
               ("Entries set aside (still in the tool, shown on each survey)", c["excluded"])]
    summary += [(f"   {_plain(r).removeprefix('set aside ')}", n) for r, n in c["excluded_by_reason"].items()]
    summary += [("Surveys in the tool", len(surveys)),
                (f"Surveys where {a} and {b} disagree", int((surveys["differences"] > 0).sum())),
                ("Survey codes in an unusual format (kept, check them)", c["code_format_flagged_in_A_or_B"])]
    if decisions:
        summary += [("Decisions read", sum(map(len, p.decisions.values()))),
                    ("   matched to a survey", sum(map(len, p.wj.values()))),
                    ("   not matched (check the survey columns)",
                     sum(map(len, p.decisions.values())) - sum(map(len, p.wj.values())))]
    return summary
