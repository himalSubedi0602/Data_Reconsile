"""Checks against the real raw data.

The raw data is never committed, so these tests are skipped on GitHub and run only on a
computer that has data/raw/ (they run before every push via the pre-push hook).
"""

from pathlib import Path

import pytest

from recon.checksums import MANIFEST, checksums_of_dir, compare, read_manifest
from recon.config import load_config

ROOT = Path(__file__).parent.parent
CONFIG = load_config(ROOT / "config/project.json")

pytestmark = pytest.mark.skipif(not CONFIG.raw_dir.is_dir(),
                                reason="real raw data not present (expected on GitHub)")


def test_raw_files_match_recorded_checksums():
    problems = compare(read_manifest(ROOT / MANIFEST), checksums_of_dir(CONFIG.raw_dir))
    assert not problems, (
        "Raw data changed:\n  " + "\n  ".join(problems) +
        "\nRestore the original file, or if this is a deliberate new export, run "
        "'python -m recon.checksums update' and commit config/raw_checksums.json.")


def test_loader_reproduces_phase_0_counts():
    from recon.loader import load

    counts = load(CONFIG).record["counts"]
    assert counts["entries_by_initials"] == {"(none)": 175, "HS": 554}
    assert counts["dataset_A"] == 416
    assert counts["dataset_B"] == 0
    assert counts["excluded_by_reason"]["NO_INITIALS"] == 175
    hs_set_aside = counts["excluded"] - counts["excluded_by_reason"]["NO_INITIALS"]
    assert hs_set_aside == 138


def test_qsf_lists_all_32_questions():
    from recon.qsf import read_questions

    q = read_questions(CONFIG.raw_dir / "erc_flood_survey_definition.qsf")
    assert len(q) == 32                     # Q1–Q31 + the survey-code question
    assert q["export_tag"].is_unique


def test_qsf_choices():
    from recon.qsf import read_choices

    c = read_choices(CONFIG.raw_dir / "erc_flood_survey_definition.qsf")
    assert c["has_text"].sum() == 17        # "Other, please describe" style options
    assert list(c[(c["qid"] == "QID24") & (c["kind"] == "scale")]["label"]) == [
        "1 (Do Not Trust)", "2", "3", "4", "5 (Strongly Trust)", "Not Familiar"]


def test_every_question_column_links_to_a_qsf_question():
    from recon.loader import read_export
    from recon.qsf import read_questions
    from recon.questions import link_columns

    linked = link_columns(read_export(CONFIG.export_file)[0]).set_index("column")
    qids = set(read_questions(CONFIG.raw_dir / "erc_flood_survey_definition.qsf")["qid"])
    assert (linked["qid"] == "").sum() == 17                  # Qualtrics metadata columns
    assert set(linked.loc[linked["qid"] != "", "qid"]) == qids
    assert linked.loc["Q11_7", "choice"] == "8"               # "Property damage"
