from pathlib import Path

import capabilities.filesystem as filesystem


def test_read_truncated_utf8_does_not_report_binary(tmp_path, monkeypatch):
    monkeypatch.setattr(filesystem, "HOME", tmp_path)
    target = tmp_path / "text.txt"
    target.write_text("abcя", encoding="utf-8")
    result = filesystem.read(str(target), max_bytes=4)
    assert result["success"] is True
    assert result["data"]["content"] == "abc"
    assert result["data"]["truncated"] is True


def test_move_directory_preserves_directory_metadata(tmp_path, monkeypatch):
    monkeypatch.setattr(filesystem, "HOME", tmp_path)
    source = tmp_path / "source"
    source.mkdir()
    result = filesystem.move(str(source), str(tmp_path / "destination"))
    assert result["success"] is True
    assert result["data"]["is_dir"] is True


def test_find_rejects_unknown_kind(tmp_path, monkeypatch):
    monkeypatch.setattr(filesystem, "HOME", tmp_path)
    result = filesystem.find("x", kind="other")
    assert result["success"] is False
    assert result["error"] == "invalid_kind"
