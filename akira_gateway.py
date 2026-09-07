"""Single input boundary for Akira.

All user-facing entry points normalize into RequestContext, take the
low-latency deterministic path when applicable, and otherwise execute through
AgentRuntime. The gateway does not own a second reasoning loop.
"""
from __future__ import annotations

from agent_runtime import AgentRuntime, get_agent_runtime
from request_context import create_request_context


class AkiraGateway:
    """Normalize requests and dispatch them to the canonical runtime."""

    def __init__(self, runtime: AgentRuntime | None = None):
        self.runtime = runtime or get_agent_runtime()

    def submit(
        self,
        text=None,
        voice_text=None,
        observation=None,
        source=None,
        metadata=None,
        request_id=None,
    ):
        request = create_request_context(
            text=text,
            voice_text=voice_text,
            observation=observation,
            source=source,
            metadata=metadata,
            request_id=request_id,
        )

        primary_text = request.primary_text()
        if primary_text:
            from fast_commands import handle as handle_fast_command

            fast_result = handle_fast_command(primary_text)
            if fast_result is not None:
                return fast_result

        return self.runtime.run(
            primary_text,
            session_id=(request.metadata or {}).get("session_id"),
        )

    def submit_text(self, text, metadata=None):
        return self.submit(text=text, source="text", metadata=metadata)

    def submit_voice(self, transcript, metadata=None):
        return self.submit(voice_text=transcript, source="voice", metadata=metadata)

    def submit_ui(self, text=None, observation=None, metadata=None):
        return self.submit(text=text, observation=observation, source="ui", metadata=metadata)


def create_gateway(runtime=None):
    return AkiraGateway(runtime=runtime)
