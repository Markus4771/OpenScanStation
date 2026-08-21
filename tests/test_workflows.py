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


def test_paperless_store_uploads_multipart_document(tmp_path, monkeypatch):
    storage, workflows = _modules(tmp_path, monkeypatch)
    source = workflows.SCAN_DIR / "invoice.pdf"
    source.write_bytes(b"%PDF-test")
    storage.upsert_target({
        "id": "paperless",
        "name": "Paperless-ngx",
        "type": "paperless",
        "enabled": True,
        "default": False,
        "config": {
            "url": "https://paperless.example/",
            "token": "api-token",
            "verify_tls": True,
            "document_type": "3",
            "tags": "4, 5",
        },
    }, create_only=True)
    workflows.upsert_workflow({
        "id": "paperless-upload",
        "name": "Paperless Upload",
        "enabled": True,
        "steps": [{"type": "store", "enabled": True, "config": {"target_id": "paperless"}}],
    }, create_only=True)
    captured = {}

    class Response:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self): return b'"task-123"'

    def fake_urlopen(request, **kwargs):
        captured["url"] = request.full_url
        captured["authorization"] = request.get_header("Authorization")
        captured["content_type"] = request.get_header("Content-type")
        captured["body"] = request.data
        return Response()

    monkeypatch.setattr(workflows, "urlopen", fake_urlopen)
    run = workflows.execute_workflow("paperless-upload", "invoice.pdf")
    assert run["status"] == "success"
    assert captured["url"] == "https://paperless.example/api/documents/post_document/"
    assert captured["authorization"] == "Token api-token"
    assert captured["content_type"].startswith("multipart/form-data; boundary=")
    assert b'name="document"; filename="invoice.pdf"' in captured["body"]
    assert b'name="document_type"' in captured["body"]
    assert captured["body"].count(b'name="tags"') == 2
    assert run["results"][0]["detail"].endswith("task_id=task-123")
