"""Legacy runtime name kept as a thin compatibility alias.

There is no second runtime here. AgentRuntime is the only execution owner.
"""
from __future__ import annotations

from agent_runtime import AgentRuntime


class AkiraRuntime(AgentRuntime):
    """Backward-compatible name for :class:`AgentRuntime`."""

    def status(self):
        return {"runtime": "agent_runtime"}

    def handle(self, text=None, voice_text=None, observation=None, metadata=None):
        from request_context import create_request_context
        return self.run(create_request_context(
            text=text,
            voice_text=voice_text,
            observation=observation,
            source="voice" if voice_text else "text",
            metadata=metadata,
        ))

    def route_request(self, request):
        return self.run(request)


def create_runtime(components=None):
    components = components or {}
    return AkiraRuntime(executor=components.get("executor"))


Runtime = AkiraRuntime
