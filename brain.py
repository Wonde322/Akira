"""Direct desktop command router.

This module intentionally executes desktop commands itself instead of passing
partially parsed actions into the legacy agent loop.
"""
from __future__ import annotations

import re

APPS = {
    "spotify": "Spotify", "спотифай": "Spotify", "спотифая": "Spotify",
    "спотифае": "Spotify", "спотифаи": "Spotify", "спотифаю": "Spotify",
    "discord": "Discord", "дискорд": "Discord", "дискорда": "Discord",
    "дискорду": "Discord", "дискордом": "Discord",
    "safari": "Safari", "сафари": "Safari",
    "chrome": "Google Chrome", "хром": "Google Chrome", "гугл хром": "Google Chrome",
    "terminal": "Terminal", "терминал": "Terminal",
    "finder": "Finder", "файндер": "Finder",
}
STOP_WORDS = {"стоп", "остановись", "отмена", "отмени", "хватит", "stop", "cancel"}
MORE_WORDS = {"еще", "ещё", "еще раз", "ещё раз", "повтори", "продолжай", "дальше"}
_LAST_TARGETS = {}
_LAST_ACTION = {}
_ACTION_RE = re.compile(r"(?<!\w)(открой|запусти|закрой|выключи)\s+", re.I)


def normalize(message):
    text = str(message or "").casefold().replace("ё", "е").strip()
    text = re.sub(r"^акира[,:;\-]?\s*", "", text)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"спотифа(?:й|я|е|и|ю)\b", "спотифай", text)
    text = re.sub(r"дискорд(?:а|у|ом|е)?\b", "дискорд", text)
    return text.strip(" .,!?:;")


def _name(value):
    value = re.sub(r"^(?:к|ко|в|на)\s+", "", value.strip(" .,!?:;"))
    return APPS.get(value, value)


def _targets(value):
    parts = re.split(r"\s*(?:,|\bи\b|\bа также\b|\bпотом\b)\s*", value.strip(), flags=re.I)
    return [_name(part) for part in parts if part.strip()]


def _app_actions(text):
    matches = list(_ACTION_RE.finditer(text))
    if not matches or matches[0].start() != 0:
        return None
    actions = []
    for index, match in enumerate(matches):
        raw = text[match.end():matches[index + 1].start() if index + 1 < len(matches) else len(text)]
        raw = re.sub(r"\s+(?:и|а затем)\s*$", "", raw).strip(" ,.!?:;")
        targets = _targets(raw)
        if targets:
            kind = "close" if match.group(1).casefold() in {"закрой", "выключи"} else "open"
            actions.append((kind, targets))
    return actions or None


def parse(message):
    text = normalize(message)
    if text in STOP_WORDS:
        return ("stop", None)
    if text in MORE_WORDS:
        return ("repeat", None)
    if text in {"закрой", "выключи"}:
        return ("close_context", None)

    music = re.match(r"^(?:включи|поставь|сыграй)\s+(.+?)\s+(?:на|в)\s+спотифай$", text)
    if music and music.group(1).strip():
        return ("spotify", music.group(1).strip())

    actions = _app_actions(text)
    if actions:
        return ("apps", actions)

    volume = re.search(r"(?:громкость|звук)(?:\s+на)?\s+(\d{1,3})(?:\s*%|\s*процент\w*)?$", text)
    if volume:
        return ("volume", max(0, min(100, int(volume.group(1)))))
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
        if isinstance(current, tuple) or current.returncode != 0:
            raise RuntimeError("Не удалось прочитать громкость")
        value = int(current.stdout.strip()) + int(delta)
    value = max(0, min(100, int(value)))
    result = _run(f"set volume output volume {value}")
    if isinstance(result, tuple) or result.returncode != 0:
        raise RuntimeError("Не удалось изменить громкость")
    return value


def _run_apps(actions, session_id):
    from capabilities.apps import open_target, close_target
    messages = []
    last_done = []
    for kind, targets in actions:
        done, failed = [], []
        for target in targets:
            result = open_target(target) if kind == "open" else close_target(target)
            if result.get("success"):
                done.append(target)
                last_done.append(target)
            else:
                failed.append(f"{target}: {result.get('error') or 'не удалось'}")
        if done:
            messages.append(f"{'Открыл' if kind == 'open' else 'Закрыл'}: {', '.join(done)}.")
        if failed:
            messages.append("Не удалось: " + "; ".join(failed))
    if last_done:
        _LAST_TARGETS[session_id] = [last_done[-1]]
    return " ".join(messages) or "Не удалось выполнить действие."


def ask(message, session_id="desktop"):
    command = parse(message)
    if command is None:
        import agent_loop
        return agent_loop.ask(message, session_id=session_id)

    kind, value = command
    if kind == "stop":
        _LAST_ACTION.pop(session_id, None)
        return "Остановил."
    if kind == "repeat":
        previous = _LAST_ACTION.get(session_id)
        if previous is None:
            return "Не понимаю, что повторить."
        kind, value = previous
    if kind == "close_context":
        targets = _LAST_TARGETS.get(session_id, [])
        if not targets:
            return "Не понимаю, что закрыть."
        kind, value = "apps", [("close", targets)]

    if kind == "spotify":
        from spotify_control import play
        _LAST_TARGETS[session_id] = ["Spotify"]
        _LAST_ACTION[session_id] = (kind, value)
        return play(value)
    if kind == "apps":
        _LAST_ACTION[session_id] = (kind, value)
        return _run_apps(value, session_id)
    if kind == "volume":
        _LAST_ACTION[session_id] = (kind, value)
        return f"Громкость: {_volume(value=value)}%"
    _LAST_ACTION[session_id] = (kind, value)
    return f"Громкость: {_volume(delta=value)}%"


def get_session(session_id="desktop"):
    import agent_loop
    return agent_loop.get_session(session_id)
