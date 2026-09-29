from recon.checksums import checksums_of_dir, compare, read_manifest, write_manifest


def test_checksum_is_stable_and_detects_a_one_character_change(tmp_path):
    f = tmp_path / "export.csv"
    f.write_text("a,b\n1,2\n")
    first = checksums_of_dir(tmp_path)
    assert checksums_of_dir(tmp_path) == first
    f.write_text("a,b\n1,3\n")
    assert compare(first, checksums_of_dir(tmp_path)) == [
        "CHANGED:  export.csv does not match its recorded checksum"]


def test_compare_reports_missing_and_new_files():
    assert compare({"old.csv": "x"}, {"new.csv": "y"}) == [
        "NEW:      new.csv is in the raw folder but has no recorded checksum",
        "MISSING:  old.csv is recorded but not found in the raw folder",
    ]


def test_manifest_round_trip(tmp_path):
    path = tmp_path / "raw_checksums.json"
    write_manifest({"export.csv": "abc"}, path)
    assert read_manifest(path) == {"export.csv": "abc"}
