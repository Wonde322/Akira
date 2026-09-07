"""Compatibility facade for the canonical Akira runtime.

AgentRuntime owns execution. This module exists only for callers that still
import ``AkiraRuntime``; it contains no alternate execution implementation.
"""
from __future__ import annotations

from agent_runtime import AgentRuntime


class AkiraRuntime(AgentRuntime):
    """Backward-compatible name for the canonical AgentRuntime."""

    def status(self):
        return {
            "runtime": "agent_runtime",
            "brain": True,
            "gateway": True,
        }

    def handle(self, text=None, voice_text=None, observation=None, metadata=None):
        request = voice_text if voice_text is not None else text
        return self.run(request, session_id=(metadata or {}).get("session_id"))

    def route_request(self, request):
        if hasattr(request, "primary_text"):
            text = request.primary_text()
            metadata = getattr(request, "metadata", {})
        elif isinstance(request, dict):
            text = request.get("text") or request.get("voice_text") or ""
            metadata = request.get("metadata") or {}
        else:
            text = str(request)
            metadata = {}
        return self.run(text, session_id=metadata.get("session_id"))

    def heartbeat_tick(self):
        from proactive_runtime import ProactiveHeartbeat

        heartbeat = ProactiveHeartbeat()
        return heartbeat.run_once(None) or []

    def discover_capability(self, request):
        from capability_discovery import CapabilityDiscovery

        return CapabilityDiscovery().choose(request)

    def authorize(self, tool_name, arguments=None, confirmed=False):
        from execution_safety import ExecutionSafetyGate

        return ExecutionSafetyGate().authorize(
            tool_name,
            arguments or {},
            confirmed=confirmed,
        )

    def verify(self, goal=None, tool_result=None, before=None, after=None, check=None):
        from outcome_verification import OutcomeVerifier

        result = OutcomeVerifier().verify(
            goal=goal,
            tool_result=tool_result,
            before=before,
            after=after,
            check=check,
        )
        return result.to_dict() if hasattr(result, "to_dict") else result

    def recover(self, action, arguments=None, error=None):
        from agent_loop import get_session

        session = get_session(None)
        session.record_failure(action, arguments or {}, error=error)
        return session.recovery_context()

    def run_agent_loop(self, goal, observer=None, executor=None, max_iterations=20):
        from computer_use_loop import ComputerUseLoop

        if executor is None:
            from tool_execution_adapter import ToolExecutionAdapter

            executor = ToolExecutionAdapter().execute
        if observer is None:
            raise ValueError("observer is required for computer-use execution")

        loop = ComputerUseLoop(
            observer=observer,
            executor=executor,
            max_iterations=max_iterations,
        )
        return loop.run(goal)

    def get_tool_executor(self):
        from tool_execution_adapter import ToolExecutionAdapter

        return ToolExecutionAdapter().execute

    def get_browser_executor(self):
        from browser_capability import BrowserCapability

        return BrowserCapability().execute


def create_runtime(components=None):
    return AkiraRuntime(executor=(components or {}).get("executor"))


Runtime = AkiraRuntime
