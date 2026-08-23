"""Desktop command router.

This module owns the direct path for local controls. It does not plan, observe or
verify commands: text is normalized, parsed once and dispatched directly.
"""
from __future__ import annotations

import re

APPS = {
    "spotify": "Spotify", "спотифай": "Spotify", "спотифая": "Spotify", "спотифае": "Spotify", "спотифаи": "Spotify", "спотифаю": "Spotify",
    "discord": "Discord", "дискорд": "Discord", "дискорда": "Discord", "дискорду": "Discord",
    "safari": "Safari", "сафари": "Safari",
    "chrome": "Google Chrome", "хром": "Google Chrome", "гугл хром": "Google Chrome",
    "terminal": "Terminal", "терминал": "Terminal",
    "finder": "Finder", "файндер": "Finder",
}

STOP_WORDS = {"стоп", "остановись", "отмена", "отмени", "хватит", "stop", "cancel"}


def normalize(message: object) -> str:
    text = str(message or "").casefold().replace("ё", "е").strip()
    text = re.sub(r"^акира[,:;\-]?\s*", "", text)
    text = re.sub(r"\s+", " ", text)
    # Common speech-recognition inflections and endings.
    text = re.sub(r"спотифа(?:й|я|е|и|ю)\b", "спотифай", text)
    text = re.sub(r"дискорд(?:а|у|ом|е)?\b", "дискорд", text)
    return text.strip(" .,!?:;")


def _name(value: str) -> str:
    value = value.strip(" .,!?:;")
    # Speech recognition can insert a short preposition before an app name.
    value = re.sub(r"^(?:к|ко|в|на)\s+", "", value)
    return APPS.get(value, value)


def _targets(value: str) -> list[str]:
    parts = re.split(r"\s*(?:,|\bи\b|\bа также\b|\bпотом\b)\s*", value.strip())
    return [name for part in parts if (name := _name(part))]


def parse(message: object):
    text = normalize(message)
    if text in STOP_WORDS:
        return ("stop", None)

    match = re.match(r"^(?:включи|поставь|сыграй)\s+(.+?)\s+(?:на|в)\s+спотифай$", text)
    if match and match.group(1).strip():
        return ("spotify", match.group(1).strip())

    # Accept ordinary commands and ASR-inserted particles: «закрой к спотифаю».
    match = re.match(r"^(открой|запусти|закрой|выключи)\s+(?:к|ко)?\s*(.+)$", text)
    if match:
        verb, raw = match.groups()
        action = "close" if verb in {"закрой", "выключи"} else "open"
        return (action, _targets(raw))

    match = re.search(r"(?:громкость|звук)(?:\s+на)?\s+(\d{1,3})(?:\s*%|\s*процент\w*)?$", text)
    if match:
        return ("volume", max(0, min(100, int(match.group(1)))))
    if re.search(r"\b(?:громче|прибавь|увеличь)\b", text):
        return ("volume_delta", 10)
    if re.search(r"\b(?:тише|убавь|уменьши)\b", text):
        return ("volume_delta", -10)
    if re.search(r"(?:выключи|убери)\s+(?:звук|громкость)", text):
        return ("volume", 0)
    return None


def _volume(value=None, delta=None):
    from capabilities.apps import _run
    if delta is not None:
        current = _run("output volume of (get volume settings)")
        if current.returncode != 0:
            raise RuntimeError(current.stderr.strip() or "Не удалось прочитать громкость")
        value = int(current.stdout.strip()) + int(delta)
    value = max(0, min(100, int(value)))
    result = _run(f"set volume output volume {value}")
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Не удалось изменить громкость")
    return value


def ask(message, session_id="desktop"):
    command = parse(message)
    if command is None:
        import agent_loop
        return agent_loop.ask(message, session_id=session_id)
    kind, value = command
    if kind == "stop":
        return "Остановил."
    if kind == "spotify":
        from spotify_control import play
        return play(value)
    if kind in {"open", "close"}:
        from capabilities.apps import open_target, close_target
        done, failed = [], []
        for target in value:
            result = open_target(target) if kind == "open" else close_target(target)
            if result.get("success"):
                done.append(target)
            else:
                failed.append(f"{target}: {result.get('error') or 'не удалось'}")
        if failed and not done:
            return "Не удалось выполнить: " + "; ".join(failed)
        verb = "Открыл" if kind == "open" else "Закрыл"
        answer = f"{verb}: {', '.join(done)}."
        return answer if not failed else answer + " Не удалось: " + "; ".join(failed)
    if kind == "volume":
        return f"Громкость: {_volume(value=value)}%"
    return f"Громкость: {_volume(delta=value)}%"


def get_session(session_id="desktop"):
    import agent_loop
    return agent_loop.get_session(session_id)
