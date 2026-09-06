"""Public Brain facade for Akira.

The agent loop owns tool calling and computer-use orchestration.  This module
is intentionally thin: it provides the stable Brain abstraction expected by
Runtime and keeps backwards-compatible ``ask``/``get_session`` entry points.
"""
from __future__ import annotations


SYSTEM = "Ты Акира, мужской персональный ассистент. Отвечай на русском, естественно и по делу. Не утверждай, что выполнил действие на компьютере, если оно не выполнялось."


class Brain:
    """Stable reasoning facade backed by the project's single agent loop."""

    def ask(self, message, session_id=None):
        from agent_loop import ask as agent_ask
        return agent_ask(message, session_id=session_id)

    def run(self, message, session_id=None):
        return self.ask(message, session_id=session_id)

    def handle(self, message, session_id=None):
        return self.ask(message, session_id=session_id)

    def process(self, message, session_id=None):
        return self.ask(message, session_id=session_id)

    def decide(self, goal, context=None):
        """Compatibility hook for host loops; the main loop owns decisions."""
        raise RuntimeError(
            "Structured decisions are owned by agent_loop.ask; use Brain.ask."
        )


def ask(message, session_id="desktop"):
    """Backwards-compatible public entry point routed to the real agent loop."""
    return Brain().ask(message, session_id=session_id)


def get_session(session_id="desktop"):
    """Return the canonical agent-loop session."""
    from agent_loop import get_session as agent_get_session
    session = agent_get_session(session_id)
    if hasattr(session, "to_dict"):
        return session.to_dict()
    return session
