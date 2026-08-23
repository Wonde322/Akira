"""Desktop command entrypoint.

Simple operating-system commands are executed directly instead of being sent
through the legacy planning/observation loop. Everything else falls back to the
existing agent runtime.
"""
from __future__ import annotations

import re


def _normalize(text: str) -> str:
    text = str(text or "").strip().casefold().replace("ё", "е")
    text = re.sub(r"\s+", " ", text)
    return text


def _app_command(message: str):
    text = _normalize(message)
    text = re.sub(r"^(акира[,:]?\s*)", "", text)

    open_match = re.match(r"^(?:открой|запусти|открыть|запустить)\s+(.+?)\.?$", text)
    if open_match:
        return "open", open_match.group(1).strip()

    close_match = re.match(r"^(?:закрой|выключи|закрыть|выключить)\s+(.+?)\.?$", text)
    if close_match:
        return "close", close_match.group(1).strip()

    return None


def _display_name(name: str) -> str:
    aliases = {
        "спотифай": "Spotify",
        "spotify": "Spotify",
        "сафари": "Safari",
        "safari": "Safari",
        "терминал": "Terminal",
        "terminal": "Terminal",
        "файндер": "Finder",
        "finder": "Finder",
        "хром": "Google Chrome",
        "chrome": "Google Chrome",
        "гугл хром": "Google Chrome",
    }
    key = _normalize(name)
    return aliases.get(key, name.strip())


def _direct_command(message: str):
    command = _app_command(message)
    if command is None:
        return None

    action, raw_target = command
    target = _display_name(raw_target)
    from capabilities.apps import open_target, close_target

    result = open_target(target) if action == "open" else close_target(target)
    if not isinstance(result, dict):
        return "Не удалось выполнить действие."

    success = result.get("success")
    if success is not True:
        error = str(result.get("error") or "")
        if error:
            return f"Не удалось выполнить: {error}."
        return "Не удалось выполнить действие."

    if action == "open":
        return f"Открыл {target}."
    return f"Закрыл {target}."


def ask(message, session_id="desktop"):
    """Execute the current desktop command.

    Direct OS commands deliberately bypass the old agent/task/observe machinery.
    """
    direct = _direct_command(message)
    if direct is not None:
        return direct

    # Keep the general agent for commands that are not simple app control.
    import agent_loop as runtime
    return runtime.ask(message, session_id=session_id)


def get_session(session_id="desktop"):
    import agent_loop as runtime
    return runtime.get_session(session_id)

__all__ = ["ask", "get_session"]
