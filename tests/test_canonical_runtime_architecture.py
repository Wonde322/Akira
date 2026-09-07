from pathlib import Path

from akira_gateway import AkiraGateway
from agent_runtime import AgentRuntime


ROOT = Path(__file__).resolve().parents[1]


def test_gateway_uses_agent_runtime_as_execution_boundary():
    class Runtime:
        def __init__(self):
            self.calls = []

        def run(self, goal, session_id=None, **kwargs):
            self.calls.append((goal, session_id, kwargs))
            return {"success": True}

    runtime = Runtime()
    result = AkiraGateway(runtime=runtime).submit_text(
        "сделай что-нибудь",
        metadata={"session_id": "test"},
    )

    assert result == {"success": True}
    assert runtime.calls == [("сделай что-нибудь", "test", {})]


def test_default_gateway_runtime_is_agent_runtime():
    from akira_gateway import create_gateway

    assert isinstance(create_gateway().runtime, AgentRuntime)


def test_runtime_no_longer_monkeypatches_agent_loop():
    source = (ROOT / "agent_runtime.py").read_text(encoding="utf-8")
    assert "_install_cancellation_guards" not in source
    assert "_akira_cancellation_guards" not in source
    assert "agent_loop._tools_for_reasoning =" not in source


def test_obsolete_brain_adapter_is_removed():
    assert not (ROOT / "brain_adapter.py").exists()
