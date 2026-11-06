"""Project settings, read from config/project.json.

Paths in the file are relative to the project root (the folder that contains config/).
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path

DEFAULT_CONFIG = Path("config/project.json")
DATASETS = ("A", "B")


class ConfigError(Exception):
    """config/project.json is missing a setting or has an invalid one."""


@dataclass(frozen=True)
class EntrantConfig:
    dataset: str               # "A" or "B"
    paper_log: Path | None     # paper log of survey numbers this entrant entered, if kept


@dataclass(frozen=True)
class ProjectConfig:
    path: Path                 # the config file itself
    export_file: Path
    qsf_file: Path
    raw_dir: Path
    working_dir: Path
    id_column: str             # column holding the survey code + entrant initials
    code_pattern: str          # regex a well-formed survey code matches (initials removed)
    entrants: dict[str, EntrantConfig]   # initials (upper case) -> settings
    extra_export_files: tuple[Path, ...] = ()   # e.g. the coworker's own export
    survey_name: str = "Survey"                 # shown in the correction tool
    code_example: str = ""                      # a well-formed survey code, e.g. "1-0235"
    decisions: dict | None = None               # team decisions sheet (see README)

    def survey_number(self, code: str) -> str:
        """The well-formed start of a code, '' if none: 1-0897-1661 -> 1-0897."""
        m = re.match(self.code_pattern.removesuffix("$") + r"(?!\d)", code)
        return m.group(0) if m else ""


def load_config(path=DEFAULT_CONFIG, root=None) -> ProjectConfig:
    path = Path(path)
    root = Path(root) if root is not None else path.resolve().parent.parent
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ConfigError(f"Config file not found: {path}") from None
    except json.JSONDecodeError as e:
        raise ConfigError(f"{path} is not valid JSON: {e}") from None

    missing = [k for k in ("export_file", "qsf_file", "raw_dir", "working_dir", "id_column",
                           "code_pattern", "entrants") if k not in raw]
    if missing:
        raise ConfigError(f"{path} is missing: {', '.join(missing)}")

    entrants = {}
    for initials, settings in raw["entrants"].items():
        dataset = settings.get("dataset")
        if dataset not in DATASETS:
            raise ConfigError(f"{path}: entrant {initials!r} has dataset {dataset!r}; "
                              f"expected one of {', '.join(DATASETS)}")
        log = settings.get("paper_log")
        entrants[initials.upper()] = EntrantConfig(dataset, root / log if log else None)

    for dataset in DATASETS:
        if sum(e.dataset == dataset for e in entrants.values()) != 1:
            raise ConfigError(f"{path}: exactly one entrant must be mapped to dataset {dataset}")

    return ProjectConfig(
        path=path,
        export_file=root / raw["export_file"],
        qsf_file=root / raw["qsf_file"],
        raw_dir=root / raw["raw_dir"],
        working_dir=root / raw["working_dir"],
        id_column=raw["id_column"],
        code_pattern=raw["code_pattern"],
        entrants=entrants,
        extra_export_files=tuple(root / f for f in raw.get("extra_export_files", [])),
        survey_name=raw.get("survey_name", "Survey"),
        code_example=raw.get("code_example", ""),
        decisions={**raw["decisions"], "file": root / raw["decisions"]["file"]} if raw.get("decisions") else None,
    )
