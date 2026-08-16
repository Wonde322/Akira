import json
import os

import pytest


def _load_entries(audit):
    if not os.path.exists(audit.AUDIT_FILE):
        return []

    with open(audit.AUDIT_FILE, encoding="utf-8") as file:
        return [json.loads(line) for line in file if line.strip()]


def test_record_tool_execution_writes_jsonl(isolated_project):
    audit = isolated_project("audit")

    audit.record_tool_execution(
        "open_app",
        {"app_name": "Safari"},
        {"success": True, "error": None, "output": "Открыл"},
        "auto",
        source="cli",
    )

    entries = _load_entries(audit)

    assert len(entries) == 1

    entry = entries[0]

    assert entry["tool"] == "open_app"
    assert entry["arguments"] == {"app_name": "Safari"}
    assert entry["success"] is True
    assert entry["output"] == "Открыл"
    assert entry["permission"] == "auto"
    assert entry["source"] == "cli"
    assert entry["timestamp"]


def test_sensitive_arguments_are_redacted(isolated_project):
    audit = isolated_project("audit")

    audit.record_tool_execution(
        "some_tool",
        {"token": "abc", "api_key": "secret", "safe": "value"},
        {"success": False, "error": "boom", "output": ""},
        "confirmed",
    )

    entry = _load_entries(audit)[0]

    assert entry["arguments"]["token"] == "***"
    assert entry["arguments"]["api_key"] == "***"
    assert entry["arguments"]["safe"] == "value"


def test_large_output_is_truncated(isolated_project):
    audit = isolated_project("audit")

    huge_output = "x" * 10000

    audit.record_tool_execution(
        "some_tool",
        {},
        {"success": True, "error": None, "output": huge_output},
        "auto",
    )

    entry = _load_entries(audit)[0]

    assert entry["output"].endswith("...")
    assert len(entry["output"]) == audit.MAX_OUTPUT_LENGTH + 3


def test_failed_result_is_recorded_as_failure(isolated_project):
    audit = isolated_project("audit")

    audit.record_tool_execution(
        "some_tool",
        {},
        {"success": False, "error": "denied", "output": "нет"},
        "denied",
    )

    entry = _load_entries(audit)[0]

    assert entry["success"] is False
    assert entry["error"] == "denied"


def test_recording_never_raises_even_if_writing_fails(
    isolated_project, monkeypatch
):
    audit = isolated_project("audit")

    def boom(*args, **kwargs):
        raise OSError("диск недоступен")

    monkeypatch.setattr(audit, "_write_json_line", boom)

    audit.record_tool_execution(
        "some_tool",
        {},
        {"success": True, "error": None, "output": "ок"},
        "auto",
    )


def test_all_executions_are_recorded(isolated_project, monkeypatch):
    audit = isolated_project("audit")

    calls = []
    monkeypatch.setattr(
        audit,
        "_write_json_line",
        lambda entry: calls.append(entry),
    )

    for i in range(3):
        audit.record_tool_execution(
            "open_app",
            {"app_name": f"App{i}"},
            {"success": True, "error": None, "output": "ок"},
            "auto",
            source="web",
        )

    assert len(calls) == 3
    assert all(call["source"] == "web" for call in calls)