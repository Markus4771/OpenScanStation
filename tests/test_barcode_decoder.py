from __future__ import annotations

from pathlib import Path

import pytest

from openscanstation import barcode_decoder


def test_decode_rejects_unknown_format(tmp_path: Path):
    target = tmp_path / "scan.txt"
    target.write_text("test", encoding="utf-8")
    with pytest.raises(ValueError):
        barcode_decoder.decode_file(target)


def test_decode_image_parses_unique_values(tmp_path: Path, monkeypatch):
    target = tmp_path / "scan.png"
    target.write_bytes(b"PNG")

    monkeypatch.setattr(barcode_decoder.shutil, "which", lambda name: "/usr/bin/zbarimg" if name == "zbarimg" else None)

    class Result:
        returncode = 0
        stdout = "INV:123\nINV:123\nhttps://example.org\n"
        stderr = ""

    monkeypatch.setattr(barcode_decoder, "_run", lambda command, timeout=45: Result())
    result = barcode_decoder.decode_file(target)

    assert result["count"] == 2
    assert result["values"] == ["INV:123", "https://example.org"]
    assert result["backend"] == "zbarimg"


def test_decoder_status_reports_pdf_support(monkeypatch):
    monkeypatch.setattr(barcode_decoder.shutil, "which", lambda name: f"/usr/bin/{name}")
    status = barcode_decoder.decoder_status()
    assert status["available"] is True
    assert status["pdf_available"] is True
