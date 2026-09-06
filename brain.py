"""Public Brain facade for Akira.

The canonical reasoning/tool loop lives in :mod:`agent_loop`.  This module
keeps the historical Brain API as a compatibility boundary without restoring
application-specific routing.
"""
from __future__ import annotations

from config import COMPUTER_USE_MAX_STEPS, MODEL
from permissions import get_permission
from tool_registry import get_tool_implementation, get_tool_schemas
from capabilities.protocol import result_to_text

SYSTEM = "Ты Акира, мужской персональный ассистент. Отвечай на русском, естественно и по делу. В обычном разговоре отвечай как AI-модель, используя свои знания и рассуждение. Не подменяй ответы заранее прописанными шаблонами. Не утверждай, что выполнил действие на компьютере, если оно не выполнялось."
SYSTEM_PROMPT = SYSTEM
TOOLS = get_tool_schemas()
client = None


def _ensure_client():
    """Compatibility alias for the canonical lazy Groq client."""
    import agent_loop
    return agent_loop._ensure_client()


def _tool_result_text(result):
    return result_to_text(result)


class Brain:
    """Stable reasoning facade backed by the project's canonical agent loop."""

    def ask(self, message, session_id=None):
        return ask(message, session_id=session_id or "desktop")

    def run(self, message, session_id=None):
        return self.ask(message, session_id=session_id)

    def handle(self, message, session_id=None):
        return self.ask(message, session_id=session_id)

    def process(self, message, session_id=None):
        return self.ask(message, session_id=session_id)

    def decide(self, goal, context=None):
        raise RuntimeError("Structured decisions are owned by agent_loop.ask; use Brain.ask.")


def ask(message, session_id="desktop"):
    """Canonical agent-loop entry point with legacy monkeypatch compatibility."""
    import agent_loop
    # Keep the old module-level extension points functional for callers that
    # customize Brain's permission/tool hooks, while execution remains owned by
    # agent_loop and the registry.
    agent_loop.get_permission = get_permission
    agent_loop.get_tool_implementation = get_tool_implementation
    return agent_loop.ask(message, session_id=session_id)


def get_session(session_id=None):
    """Return the canonical Session object (None means the default session)."""
    from agent_loop import get_session as agent_get_session
    return agent_get_session(session_id)


# Historical default conversation alias.  It intentionally points at the
# canonical session history rather than maintaining a second chat store.
conversation = get_session(None).history
