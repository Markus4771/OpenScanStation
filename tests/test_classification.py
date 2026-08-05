from pathlib import Path


def test_invoice_classification(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENSCANSTATION_DATA_DIR", str(tmp_path))
    import importlib
    import openscanstation.classification as module
    module = importlib.reload(module)
    result = module.classify(text="RECHNUNG Rechnungsnummer 4711 Gesamtbetrag 99,00 EUR", filename="eingang.pdf")
    assert result["document_type"] == "rechnung"
    assert result["rule_id"] == "rechnung"
    assert result["confidence"] > 0


def test_barcode_has_high_weight(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENSCANSTATION_DATA_DIR", str(tmp_path))
    import importlib
    import openscanstation.classification as module
    module = importlib.reload(module)
    result = module.classify(text="unbekannter Inhalt", filename="scan.pdf", barcodes=["DEL:2026-0815"])
    assert result["document_type"] == "lieferschein"
    assert result["matches"]["barcodes"] == ["DEL:"]


def test_rule_crud_and_persistence(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENSCANSTATION_DATA_DIR", str(tmp_path))
    import importlib
    import openscanstation.classification as module
    module = importlib.reload(module)
    module.upsert_rule({
        "id": "bescheid", "name": "Bescheid", "document_type": "bescheid",
        "enabled": True, "priority": 200, "keywords_any": ["bescheid"],
        "keywords_all": [], "filename_contains": [], "tag_contains": [], "barcode_prefixes": []
    }, create_only=True)
    assert module.classify(text="Ihr Bescheid")["document_type"] == "bescheid"
    assert Path(module.RULES_FILE).is_file()
    module.delete_rule("bescheid")
    assert all(rule["id"] != "bescheid" for rule in module.load_rules()["rules"])


def test_unknown_document_falls_back(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENSCANSTATION_DATA_DIR", str(tmp_path))
    import importlib
    import openscanstation.classification as module
    module = importlib.reload(module)
    result = module.classify(text="xyz", filename="scan.pdf")
    assert result["document_type"] == "dokument"
    assert result["rule_id"] is None
