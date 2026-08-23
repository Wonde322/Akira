"""Single desktop command entry point.

The desktop path does not create plans, verification tasks or mandatory
observations. One user message produces one action/result.
"""
from __future__ import annotations

import re

_ALIAS = {
    "спотифай": "Spotify", "spotify": "Spotify",
    "сафари": "Safari", "safari": "Safari",
    "хром": "Google Chrome", "chrome": "Google Chrome",
    "гугл хром": "Google Chrome",
    "терминал": "Terminal", "terminal": "Terminal",
    "файндер": "Finder", "finder": "Finder",
}


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().casefold().replace("ё", "е"))


def _command(message: str):
    text = _clean(message)
    text = re.sub(r"^акира[,:]?\s*", "", text)
    match = re.match(r"^(открой|запусти|закрой|выключи)\s+(.+?)[.!?]*$", text)
    if not match:
        return None
    verb, target = match.groups()
    action = "close" if verb in {"закрой", "выключи"} else "open"
    target = target.strip()
    return action, _ALIAS.get(target, target)


def ask(message, session_id="desktop"):
    command = _command(message)
    if command:
        from capabilities.apps import close_target, open_target
        action, target = command
        result = open_target(target) if action == "open" else close_target(target)
        if result.get("success"):
            return (f"Открыл {target}." if action == "open" else f"Закрыл {target}.")
        return "Не удалось выполнить действие."

    # Non-desktop-control requests keep the existing general assistant.
    import agent_loop
    return agent_loop.ask(message, session_id=session_id)


def get_session(session_id="desktop"):
    import agent_loop
    return agent_loop.get_session(session_id)
