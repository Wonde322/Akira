"""Single input boundary for Akira.

Text and future voice input share exactly the same execution path:
RequestContext -> AgentRuntime -> agent_loop.
The gateway normalizes input and owns no reasoning or action executor.
"""
from __future__ import annotations

from agent_runtime import AgentRuntime, get_agent_runtime
from request_context import create_request_context


class AkiraGateway:
    """Normalize user input and hand it to the canonical runtime."""

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
        if not request.primary_text():
            return {"success": False, "error": "empty_request", "output": "Пустой запрос."}
        return self.runtime.run(request)

    def submit_text(self, text, metadata=None):
        return self.submit(text=text, source="text", metadata=metadata)

    def submit_voice(self, transcript, metadata=None):
        return self.submit(voice_text=transcript, source="voice", metadata=metadata)

    def submit_ui(self, text=None, observation=None, metadata=None):
        return self.submit(text=text, observation=observation, source="ui", metadata=metadata)


def create_gateway(runtime: AgentRuntime | None = None):
    return AkiraGateway(runtime=runtime)
