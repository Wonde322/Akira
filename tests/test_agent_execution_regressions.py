import agent_execution


def test_unknown_tool_does_not_request_confirmation(monkeypatch):
    monkeypatch.setattr(agent_execution, "get_tool_implementation", lambda name: None)
    monkeypatch.setattr(agent_execution, "resolve_capability", lambda name: {"success": False})

    def fail_if_called(*args, **kwargs):
        raise AssertionError("unknown tool must not reach permission confirmation")

    monkeypatch.setattr(agent_execution, "get_permission", fail_if_called)
    monkeypatch.setattr(agent_execution, "request_confirmation", fail_if_called)

    result, decision = agent_execution.execute("definitely_missing", {})

    assert result["success"] is False
    assert result["error"] == "unknown"
    assert decision == "unknown"


def test_structured_result_keeps_resolution_provenance(monkeypatch):
    structured = {"success": True, "data": {"ok": True}}
    monkeypatch.setattr(agent_execution, "get_tool_implementation", lambda name: lambda: structured)
    monkeypatch.setattr(agent_execution, "get_permission", lambda name: "auto")

    result, decision = agent_execution.execute("observe", {})

    assert decision == "auto"
    assert result["requested_tool"] == "observe"
    assert result["resolved_tool"] == "observe"
