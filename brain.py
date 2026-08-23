"""Small, deterministic entry point for the desktop app.

This module has two paths only:
1. direct OS/media commands;
2. conversation.

Conversation is never treated as a computer action.
"""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed

_APPS = {
    "spotify": "Spotify", "спотифай": "Spotify", "спотифая": "Spotify", "спотифае": "Spotify", "спотифаи": "Spotify",
    "discord": "Discord", "дискорд": "Discord", "дискорда": "Discord", "дискорду": "Discord",
    "safari": "Safari", "сафари": "Safari", "chrome": "Google Chrome", "хром": "Google Chrome", "гугл хром": "Google Chrome",
    "terminal": "Terminal", "терминал": "Terminal", "finder": "Finder", "файндер": "Finder",
}
_STOP = {"стоп", "остановись", "отмена", "отмени", "хватит", "stop", "cancel"}
_MORE = {"дальше", "следующий", "следующий трек", "скип", "пропусти"}
_CONTEXT: dict[str, dict] = {}


def _text(value: str) -> str:
    value = str(value or "").casefold().replace("ё", "е").strip()
    value = re.sub(r"^акира[,:;\-]?\s*", "", value)
    value = re.sub(r"\s+", " ", value)
    value = re.sub(r"спотифа(?:й|я|е|и|ю)\b", "спотифай", value)
    value = re.sub(r"дискорд(?:а|у|ом|е)?\b", "дискорд", value)
    return value.strip(" .,!?:;")


def _remember(session_id: str, kind: str, **data) -> None:
    _CONTEXT[session_id] = {"kind": kind, **data}


def _targets(chunk: str) -> list[str]:
    names = []
    for item in re.split(r"\s*(?:,|\bи\b|\bа также\b)\s*", chunk):
        item = re.sub(r"^(?:к|ко|в|на)\s+", "", item.strip())
        if item:
            names.append(_APPS.get(item, item))
    return names


def _parse_apps(text: str):
    matches = list(re.finditer(r"(?:^|\s)(открой|запусти|закрой)\s+", text))
    if not matches or matches[0].start() != 0:
        return None
    actions = []
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        chunk = text[match.end():end].strip(" ,.!?:;")
        chunk = re.sub(r"\s+(?:и|а затем|потом)\s*$", "", chunk)
        targets = _targets(chunk)
        if not targets:
            return None
        actions.append(("open" if match.group(1) in {"открой", "запусти"} else "close", targets))
    return actions


def _run_apps(actions):
    from capabilities.apps import open_target, close_target
    lines, completed = [], []
    for operation, targets in actions:
        fn = open_target if operation == "open" else close_target
        results = {}
        with ThreadPoolExecutor(max_workers=max(1, len(targets))) as pool:
            futures = {pool.submit(fn, target): target for target in targets}
            for future in as_completed(futures):
                target = futures[future]
                try:
                    results[target] = future.result()
                except Exception as exc:
                    results[target] = {"success": False, "error": str(exc)}
        ok, bad = [], []
        for target in targets:
            result = results[target]
            if result.get("success"):
                ok.append(target)
                completed.append(target)
            else:
                bad.append(f"{target}: {result.get('error') or 'не удалось'}")
        if ok:
            lines.append(("Открыл" if operation == "open" else "Закрыл") + ": " + ", ".join(ok) + ".")
        if bad:
            lines.append("Не удалось: " + "; ".join(bad))
    return " ".join(lines) or "Не удалось выполнить действие.", completed


def _volume_get() -> int:
    from capabilities.apps import _run
    result = _run("output volume of (get volume settings)")
    if result.returncode != 0:
        raise RuntimeError("Не удалось прочитать громкость")
    return max(0, min(100, int(result.stdout.strip())))


def _volume_set(value: int) -> int:
    from capabilities.apps import _run
    value = max(0, min(100, int(value)))
    result = _run(f"set volume output volume {value}")
    if result.returncode != 0:
        raise RuntimeError("Не удалось изменить громкость")
    return value


def _small_talk(text: str):
    compact = re.sub(r"[!?.,]", "", text).strip()
    if compact in {"привет", "здравствуй", "здравствуйте", "хай", "приветики"}:
        return "Привет! Чем могу помочь?"
    if compact in {"спасибо", "спс", "благодарю"}:
        return "Пожалуйста."
    if compact in {"как дела", "как ты"}:
        return "Нормально. Готов работать."
    return None


def _conversation(message: str, session_id: str) -> str:
    """Conversation is isolated from command execution."""
    quick = _small_talk(_text(message))
    if quick is not None:
        return quick
    import agent_loop
    answer = agent_loop.ask(message, session_id=session_id)
    if not isinstance(answer, str):
        answer = str(answer or "")
    return answer.strip() or "Не получил ответ."


def ask(message: str, session_id: str = "desktop") -> str:
    text = _text(message)
    if not text:
        return ""
    if text in _STOP:
        _CONTEXT.pop(session_id, None)
        return "Остановил."

    # Conversation is checked first. It never enters the command executor.
    quick = _small_talk(text)
    if quick is not None:
        return quick

    context = _CONTEXT.get(session_id, {})

    if text in {"выключи", "поставь на паузу", "пауза"} and context.get("kind") == "spotify":
        from spotify_control import pause
        return pause()
    if text == "закрой" and context.get("kind") == "apps" and context.get("target"):
        return _run_apps([("close", [context["target"]])])[0]
    if text in _MORE and context.get("kind") == "spotify":
        from spotify_control import next_track
        return next_track()

    music = re.match(r"^(?:включи|поставь|сыграй)\s+(.+?)\s+(?:на|в)\s+спотифай$", text)
    if music:
        from spotify_control import play
        query = music.group(1).strip()
        answer = play(query)
        _remember(session_id, "spotify", query=query)
        return answer

    if text in {"дальше", "следующий", "следующий трек", "скип", "пропусти"}:
        from spotify_control import next_track
        return next_track()

    if re.search(r"^(?:(?:какая|какой|сколько|текущая)\s+)?(?:сейчас\s+)?(?:громкость|уровень звука|звук)(?:\s+сейчас)?$", text):
        return f"Громкость: {_volume_get()}%"
    match = re.search(r"(?:громкость|звук)(?:\s+на)?\s+(\d{1,3})(?:\s*%|\s*процент\w*)?$", text)
    if match:
        value = _volume_set(int(match.group(1)))
        _remember(session_id, "volume", delta=10)
        return f"Громкость: {value}%"
    if re.search(r"\b(?:громче|прибавь|увеличь)\b", text):
        value = _volume_set(_volume_get() + 10)
        _remember(session_id, "volume", delta=10)
        return f"Громкость: {value}%"
    if re.search(r"\b(?:тише|убавь|уменьши)\b", text):
        value = _volume_set(_volume_get() - 10)
        _remember(session_id, "volume", delta=-10)
        return f"Громкость: {value}%"
    if re.search(r"(?:выключи|убери)\s+(?:звук|громкость)", text):
        return f"Громкость: {_volume_set(0)}%"

    actions = _parse_apps(text)
    if actions:
        answer, completed = _run_apps(actions)
        if completed:
            _remember(session_id, "apps", target=completed[-1])
        return answer

    return _conversation(message, session_id)


def get_session(session_id: str = "desktop"):
    import agent_loop
    return agent_loop.get_session(session_id)
