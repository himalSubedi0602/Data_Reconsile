import shutil
from pathlib import Path

import pytest

from recon.config import EntrantConfig, ProjectConfig

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def project(tmp_path) -> ProjectConfig:
    """A throwaway project: fake raw files copied into tmp_path/raw, outputs in tmp_path/working."""
    raw = tmp_path / "raw"
    raw.mkdir()
    shutil.copy(FIXTURES / "fake_export.csv", raw / "export.csv")
    shutil.copy(FIXTURES / "fake_paper_log.txt", raw / "hs_paper_log.txt")
    shutil.copy(FIXTURES / "fake_survey.qsf", raw / "survey.qsf")
    return ProjectConfig(
        path=tmp_path / "project.json",
        export_file=raw / "export.csv",
        qsf_file=raw / "survey.qsf",
        raw_dir=raw,
        working_dir=tmp_path / "working",
        id_column="QID2",
        code_pattern=r"^\d+-\d{4}$",
        entrants={
            "HS": EntrantConfig("A", raw / "hs_paper_log.txt"),
            "CH": EntrantConfig("B", None),
        },
    )


@pytest.fixture
def write_export(project):
    """Replace the project's export with the given text; returns the updated config."""
    def _write(text: str) -> ProjectConfig:
        project.export_file.write_text(text, encoding="utf-8")
        return project
    return _write
