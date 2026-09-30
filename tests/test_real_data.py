"""Checks against the real raw data, one per phase.

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


def test_phase_1_loader_and_question_map():
    import json

    from recon.loader import load, read_export
    from recon.qsf import read_choices, read_questions
    from recon.questions import build_question_map

    counts = load(CONFIG).record["counts"]
    assert counts["entries_by_initials"] == {"(none)": 175, "HS": 554}
    assert (counts["dataset_A"], counts["dataset_B"]) == (416, 0)
    assert counts["excluded"] - counts["excluded_by_reason"]["NO_INITIALS"] == 138   # HS set aside

    qmap = build_question_map(read_export(CONFIG.export_file)[0], read_questions(CONFIG.qsf_file),
                              read_choices(CONFIG.qsf_file), CONFIG.id_column)
    json.dumps(qmap)
    assert (len(qmap["questions"]), len(qmap["columns"]), len(qmap["other_pairs"])) == (32, 173, 17)
    roles = [c["role"] for c in qmap["columns"]]
    assert (roles.count("COMPARE"), roles.count("METADATA"), roles.count("IDENTIFIER")) == (155, 17, 1)
    q11_7 = next(c for c in qmap["columns"] if c["column"] == "Q11_7")
    assert q11_7["choice"] == "8"                         # grid row 8, "Property damage"
