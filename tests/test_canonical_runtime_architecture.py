from pathlib import Path

from akira_gateway import AkiraGateway
from agent_runtime import AgentRuntime


ROOT = Path(__file__).resolve().parents[1]


def test_gateway_passes_one_normalized_request_to_runtime():
    class Runtime:
        def __init__(self):
            self.requests = []

        def run(self, request, **kwargs):
            self.requests.append((request, kwargs))
            return {"success": True}

    runtime = Runtime()
    result = AkiraGateway(runtime=runtime).submit_text(
        "сделай что-нибудь",
        metadata={"session_id": "test"},
    )

    request, kwargs = runtime.requests[0]
    assert result == {"success": True}
    assert request.primary_text() == "сделай что-нибудь"
    assert request.source == "text"
    assert request.metadata["session_id"] == "test"
    assert kwargs == {}


def test_default_gateway_runtime_is_agent_runtime():
    from akira_gateway import create_gateway
    assert isinstance(create_gateway().runtime, AgentRuntime)


def test_runtime_no_longer_monkeypatches_agent_loop():
    source = (ROOT / "agent_runtime.py").read_text(encoding="utf-8")
    assert "_install_cancellation_guards" not in source
    assert "_akira_cancellation_guards" not in source
    assert "agent_loop._tools_for_reasoning =" not in source


def test_brain_is_only_a_compatibility_import_surface():
    source = (ROOT / "brain.py").read_text(encoding="utf-8")
    assert "agent_loop.SYSTEM_PROMPT =" not in source
    assert "agent_loop.client =" not in source
    assert "agent_loop.get_permission =" not in source


def test_duplicate_execution_loops_are_removed():
    assert not (ROOT / "brain_adapter.py").exists()
    assert not (ROOT / "fast_commands.py").exists()
    assert not (ROOT / "computer_use_loop.py").exists()
    assert not (ROOT / "unified_agent_loop.py").exists()
