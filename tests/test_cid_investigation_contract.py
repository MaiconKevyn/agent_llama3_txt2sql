from pathlib import Path


def test_cid_investigation_files_exist():
    root = Path("evaluation/cid_investigation")
    assert (root / "README.md").exists()
    assert (root / "build_cid_baseline.py").exists()
    assert (root / "results" / ".gitkeep").exists()


def test_cid_baseline_script_documents_required_sql_contracts():
    source = Path("evaluation/cid_investigation/build_cid_baseline.py").read_text()
    assert "COUNT(DISTINCT CID)" in source
    assert "DS_CAPITULO" in source
    assert "DS_GRUPO" in source
    assert "DS_CATEGORIA" in source
    assert "DIAG_PRINC = c.CID" in source
