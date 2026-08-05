import importlib
from pathlib import Path


def _modules(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENSCANSTATION_DATA_DIR", str(tmp_path))
    import openscanstation.storage_targets as storage_targets
    import openscanstation.workflows as workflows
    importlib.reload(storage_targets); importlib.reload(workflows)
    workflows.SCAN_DIR = tmp_path / "scans"
    workflows.SCAN_DIR.mkdir(parents=True, exist_ok=True)
    return storage_targets, workflows


def test_default_workflow_and_persistence(tmp_path, monkeypatch):
    _, workflows = _modules(tmp_path, monkeypatch)
    assert workflows.workflow_by_id("standard")
    workflows.upsert_workflow({"id":"archiv","name":"Archiv","enabled":True,"steps":[{"type":"store","enabled":True,"config":{"target_id":"local"}}]}, create_only=True)
    assert workflows.workflow_by_id("archiv")["name"] == "Archiv"


def test_local_store_workflow(tmp_path, monkeypatch):
    storage, workflows = _modules(tmp_path, monkeypatch)
    source = workflows.SCAN_DIR / "scan.pdf"; source.write_bytes(b"pdf")
    destination = tmp_path / "archive"
    storage.upsert_target({"id":"archive","name":"Archiv","type":"local","enabled":True,"default":False,"config":{"path":str(destination)}}, create_only=True)
    workflows.upsert_workflow({"id":"copy","name":"Kopieren","enabled":True,"steps":[{"type":"store","enabled":True,"config":{"target_id":"archive"}}]}, create_only=True)
    run = workflows.execute_workflow("copy", "scan.pdf")
    assert run["status"] == "success"
    assert (destination / "scan.pdf").read_bytes() == b"pdf"
    assert workflows.list_runs()[0]["workflow_id"] == "copy"


def test_invalid_step_rejected(tmp_path, monkeypatch):
    _, workflows = _modules(tmp_path, monkeypatch)
    try:
        workflows.upsert_workflow({"id":"bad","name":"Bad","steps":[{"type":"shell","config":{}}]}, create_only=True)
    except ValueError as exc:
        assert "nicht unterstützter" in str(exc).lower()
    else:
        raise AssertionError("invalid step accepted")
