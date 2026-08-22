from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class InputContext:
    text: str | None = None
    voice_text: str | None = None
    observation: Any = None
    source: str = "text"
    metadata: dict = field(default_factory=dict)
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def primary_text(self):
        return self.text or self.voice_text or ""

    def to_dict(self):
        return {
            "text": self.text,
            "voice_text": self.voice_text,
            "observation": self.observation,
            "source": self.source,
            "metadata": self.metadata,
            "created_at": self.created_at,
        }


def build_input_context(
    text=None,
    voice_text=None,
    observation=None,
    source=None,
    metadata=None,
):
    if source is None:
        if voice_text:
            source = "voice"
        elif observation is not None and not text:
            source = "screen"
        else:
            source = "text"

    return InputContext(
        text=text,
        voice_text=voice_text,
        observation=observation,
        source=source,
        metadata=metadata or {},
    )


def merge_input_context(base, incoming):
    if isinstance(base, InputContext):
        base = base.to_dict()

    if isinstance(incoming, InputContext):
        incoming = incoming.to_dict()

    base = dict(base or {})
    incoming = dict(incoming or {})

    merged = {
        **base,
        **{
            key: value
            for key, value in incoming.items()
            if value is not None
        },
    }

    merged["metadata"] = {
        **base.get("metadata", {}),
        **incoming.get("metadata", {}),
    }

    return build_input_context(
        text=merged.get("text"),
        voice_text=merged.get("voice_text"),
        observation=merged.get("observation"),
        source=merged.get("source"),
        metadata=merged.get("metadata"),
    )
