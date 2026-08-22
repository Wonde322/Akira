\
"""
Unified request model for Akira.

All input channels are normalized here before entering
the runtime or agent loop.
"""

from dataclasses import dataclass, field
from typing import Any
import time
import uuid


@dataclass
class RequestContext:
    request_id: str
    source: str
    text: str | None = None
    voice_text: str | None = None
    observation: Any = None
    metadata: dict = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)

    def primary_text(self):
        return (
            self.text
            or self.voice_text
            or ""
        )

    def to_dict(self):
        return {
            "request_id": self.request_id,
            "source": self.source,
            "text": self.text,
            "voice_text": self.voice_text,
            "observation": self.observation,
            "metadata": self.metadata,
            "created_at": self.created_at,
        }


def create_request_context(
    text=None,
    voice_text=None,
    observation=None,
    source=None,
    metadata=None,
    request_id=None,
):
    if source is None:
        if voice_text:
            source = "voice"
        elif text:
            source = "text"
        else:
            source = "system"

    return RequestContext(
        request_id=request_id or str(uuid.uuid4()),
        source=source,
        text=text,
        voice_text=voice_text,
        observation=observation,
        metadata=metadata or {},
    )
