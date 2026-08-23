"""Direct desktop command router.

Supported operating-system commands execute here, with no planner, observer,
verification task or background agent involved.
"""
from __future__ import annotations

import re

_ALIAS = {
    "спотифай": "Spotify", "spotify": "Spotify",
    "дискорд": "Discord", "discord": "Discord",
    "сафари": "Safari", "safari": "Safari",
    "хром": "Google Chrome", "chrome": "Google Chrome", "гугл хром": "Google Chrome",
    "терминал": "Terminal", "terminal": "Terminal",
    "файндер": "Finder", "finder": "Finder",
}


def _text(value):
    return re.sub(r"\s+", " ", str(value or "").strip().casefold().replace("ё", "е"))


def _strip_name(value):
    return value.strip(" .,!?")


def _parse(message):
    text = re.sub(r"^акира[,:]?\s*", "", _text(message))
    match = re.match(r"^(?P<verb>открой|запусти|закрой|выключи)\s+(?P<target>.+)$", text)
    if match:
        verb = match.group("verb")
        target = _strip_name(match.group("target"))
        return ("close" if verb in {"закрой", "выключи"} else "open", _ALIAS.get(target, target))

    # Volume: exact value or relative change.
    absolute = re.search(r"(?:громкость|звук)(?:\s+на)?\s+(\d{1,3})\s*(?:%|процент|процента|процентов)?$", text)
    if absolute:
        return "volume", int(absolute.group(1))
    if re.search(r"(?:сделай|поставь|установи)\s+(?:громкость|звук)\s+максим", text):
        return "volume", 100
    if re.search(r"(?:убери|выключи)\s+(?:звук|громкость)|(?:громкость|звук)\s+на\s+ноль", text):
        return "volume", 0
    if re.search(r"(?:сделай|прибавь|увеличь|громче)", text):
        return "volume_delta", 10
    if re.search(r"(?:убавь|уменьши|тише)", text):
        return "volume_delta", -10
    return None


def _volume(value=None, delta=None):
    from capabilities.apps import _run
    if delta is not None:
        current = _run("output volume of (get volume settings)")
        if isinstance(current, tuple) or current.returncode != 0:
            return None
        try:
            value = int(current.stdout.strip()) + int(delta)
        except ValueError:
            return None
    value = max(0, min(100, int(value)))
    result = _run(f"set volume output volume {value}")
    if isinstance(result, tuple) or result.returncode != 0:
        return None
    return value


def ask(message, session_id="desktop"):
    command = _parse(message)
    if command:
        kind, value = command
        if kind in {"open", "close"}:
            from capabilities.apps import open_target, close_target
            result = open_target(value) if kind == "open" else close_target(value)
            if result.get("success"):
                return f"Открыл {value}." if kind == "open" else f"Закрыл {value}."
            error = result.get("error") or "Не удалось выполнить действие."
            return f"Не удалось выполнить: {error}"
        level = _volume(value=value) if kind == "volume" else _volume(delta=value)
        return f"Громкость: {level}%" if level is not None else "Не удалось изменить громкость."

    import agent_loop
    return agent_loop.ask(message, session_id=session_id)


def get_session(session_id="desktop"):
    import agent_loop
    return agent_loop.get_session(session_id)
