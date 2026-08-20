import json

import audit


def _entries(tmp_path, monkeypatch):
    path = tmp_path / "audit.jsonl"
    monkeypatch.setattr(audit, "AUDIT_FILE", str(path))
    return path


def test_nested_sensitive_values_are_redacted():
    safe = audit._safe_arguments({"outer": {"token": "secret", "ok": "yes"}}, "read")
    assert safe == {"outer": {"token": "***", "ok": "yes"}}


def test_sensitive_values_inside_lists_are_redacted():
    safe = audit._safe_arguments({"items": [{"password": "x"}, {"ok": 1}]}, "read")
    assert safe["items"][0]["password"] == "***"
    assert safe["items"][1] == {"ok": 1}


def test_type_text_is_redacted_even_when_nested():
    safe = audit._safe_arguments({"meta": {"text": "hello"}}, "type")
    assert safe["meta"]["text"] == "***"


def test_non_mapping_arguments_are_preserved_safely():
    assert audit._safe_arguments(["a", 1], "read") == {"value": ["a", 1]}


def test_non_json_argument_values_do_not_break_recording(tmp_path, monkeypatch):
    path = _entries(tmp_path, monkeypatch)
    audit.record_tool_execution("x", {"value": object()}, {"success": True}, "auto")
    entry = json.loads(path.read_text(encoding="utf-8"))
    assert entry["success"] is True
    assert isinstance(entry["arguments"]["value"], str)


def test_non_mapping_result_is_logged(tmp_path, monkeypatch):
    path = _entries(tmp_path, monkeypatch)
    audit.record_tool_execution("x", {}, "legacy result", "auto")
    entry = json.loads(path.read_text(encoding="utf-8"))
    assert entry["output"] == "legacy result"
    assert entry["success"] is False


def test_data_with_non_json_values_is_serialized(tmp_path, monkeypatch):
    path = _entries(tmp_path, monkeypatch)
    audit.record_tool_execution("x", {}, {"success": True, "data": {"value": object()}}, "auto")
    entry = json.loads(path.read_text(encoding="utf-8"))
    assert entry["success"] is True
    assert "value" in entry["output"]


def test_deep_arguments_are_bounded_and_recorded(tmp_path, monkeypatch):
    path = _entries(tmp_path, monkeypatch)
    value = {}
    current = value
    for _ in range(12):
        current["next"] = {}
        current = current["next"]
    audit.record_tool_execution("x", value, {"success": True}, "auto")
    entry = json.loads(path.read_text(encoding="utf-8"))
    current = entry["arguments"]
    for _ in range(9):
        current = current["next"]
    assert current == "<truncated>"
