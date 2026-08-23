"""Direct desktop command router with typed session context.

No agent-loop state is used for short follow-up commands. Context records what the
last operation *was*, so words such as "дальше" and "выключи" resolve by action
kind instead of replaying raw text.
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
    "terminal": "Terminal", "терминал": "Terminal", "finder": "Finder", "файндер": "Finder",
}
STOP_WORDS = {"стоп", "остановись", "отмена", "отмени", "хватит", "stop", "cancel"}
MORE_WORDS = {"еще", "ещё", "еще раз", "ещё раз", "повтори", "продолжай", "дальше"}
_CONTEXT = {}
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
        return "stop", None
    if text in MORE_WORDS:
        return "more", None
    if text in {"закрой", "выключи"}:
        return "context_stop", None
    if text in {"следующий", "следующий трек", "скип", "пропусти"}:
        return "spotify_next", None
    music = re.match(r"^(?:включи|поставь|сыграй)\s+(.+?)\s+(?:на|в)\s+спотифай$", text)
    if music and music.group(1).strip():
        return "spotify_play", music.group(1).strip()
    actions = _app_actions(text)
    if actions:
        return "apps", actions
    volume = re.search(r"(?:громкость|звук)(?:\s+на)?\s+(\d{1,3})(?:\s*%|\s*процент\w*)?$", text)
    if volume:
        return "volume", max(0, min(100, int(volume.group(1))))
    if re.search(r"\b(?:громче|прибавь|увеличь)\b", text):
        return "volume_delta", 10
    if re.search(r"\b(?:тише|убавь|уменьши)\b", text):
        return "volume_delta", -10
    if re.search(r"(?:выключи|убери)\s+(?:звук|громкость)", text):
        return "volume", 0
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


def _run_apps(actions):
    from capabilities.apps import open_target, close_target
    messages, last_done = [], []
    for kind, targets in actions:
        done, failed = [], []
        for target in targets:
            result = open_target(target) if kind == "open" else close_target(target)
            (done if result.get("success") else failed).append(target if result.get("success") else f"{target}: {result.get('error') or 'не удалось'}")
            if result.get("success"):
                last_done.append(target)
        if done:
            messages.append(f"{'Открыл' if kind == 'open' else 'Закрыл'}: {', '.join(done)}.")
        if failed:
            messages.append("Не удалось: " + "; ".join(failed))
    return " ".join(messages) or "Не удалось выполнить действие.", last_done


def _set_context(session_id, kind, value=None, target=None):
    _CONTEXT[session_id] = {"kind": kind, "value": value, "target": target}


def ask(message, session_id="desktop"):
    command = parse(message)
    if command is None:
        import agent_loop
        return agent_loop.ask(message, session_id=session_id)
    kind, value = command
    context = _CONTEXT.get(session_id, {})
    if kind == "stop":
        _CONTEXT.pop(session_id, None)
        return "Остановил."
    if kind == "more":
        if context.get("kind") == "spotify_play":
            from spotify_control import next_track
            return next_track()
        if context.get("kind") == "volume_delta":
            value, kind = context.get("value", 10), "volume_delta"
        else:
            return "Не понимаю, что продолжить."
    if kind == "context_stop":
        if context.get("kind") == "spotify_play":
            from spotify_control import pause
            return pause()
        if context.get("kind") == "apps" and context.get("target"):
            kind, value = "apps", [("close", [context["target"]])]
        else:
            return "Не понимаю, что выключить."
    if kind == "spotify_play":
        from spotify_control import play
        result = play(value)
        _set_context(session_id, "spotify_play", value, "Spotify")
        return result
    if kind == "spotify_next":
        from spotify_control import next_track
        result = next_track()
        _set_context(session_id, "spotify_play", context.get("value"), "Spotify")
        return result
    if kind == "apps":
        result, done = _run_apps(value)
        if done:
            _set_context(session_id, "apps", value, done[-1])
        return result
    if kind == "volume":
        result = f"Громкость: {_volume(value=value)}%"
        _set_context(session_id, "volume", value)
        return result
    result = f"Громкость: {_volume(delta=value)}%"
    _set_context(session_id, "volume_delta", value)
    return result


def get_session(session_id="desktop"):
    import agent_loop
    return agent_loop.get_session(session_id)
