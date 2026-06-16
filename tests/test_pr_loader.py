from src.parsing.pr_loader import load_path

SAMPLE_PR_DIR = "tests/fixtures/sample_pr"


def test_load_directory_finds_all_files():
    files = load_path(SAMPLE_PR_DIR)
    paths = [f["path"] for f in files]

    assert len(files) == 3
    assert any("db.py" in p for p in paths)
    assert any("config.py" in p for p in paths)
    assert any("handlers.py" in p for p in paths)
    assert all(f["language"] == "python" for f in files)