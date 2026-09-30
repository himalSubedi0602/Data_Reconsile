from recon.checksums import checksums_of_dir, compare


def test_checksum_is_stable_and_detects_a_one_character_change(tmp_path):
    f = tmp_path / "export.csv"
    f.write_text("a,b\n1,2\n")
    first = checksums_of_dir(tmp_path)
    assert checksums_of_dir(tmp_path) == first
    f.write_text("a,b\n1,3\n")
    assert compare(first, checksums_of_dir(tmp_path)) == [
        "CHANGED:  export.csv does not match its recorded checksum"]
