from pathlib import Path


def test_media_worker_entrypoint_adds_project_root_before_imports():
    source = (Path(__file__).parents[1] / "scripts" / "media-worker.py").read_text(encoding="utf-8")
    assert "Path(__file__).resolve().parents[1]" in source
    assert "sys.path.insert(0" in source
    assert source.index("sys.path.insert(0") < source.index("from services.media_jobs import")
