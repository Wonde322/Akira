"""Deterministic desktop router: direct commands or direct conversation."""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed

APPS = {
    "spotify": "Spotify", "спотифай": "Spotify", "discord": "Discord", "дискорд": "Discord",
    "safari": "Safari", "сафари": "Safari", "chrome": "Google Chrome", "хром": "Google Chrome",
    "гугл хром": "Google Chrome", "terminal": "Terminal", "терминал": "Terminal",
    "finder": "Finder", "файндер": "Finder",
}
STOP = {"стоп", "остановись", "отмена", "отмени", "хватит", "stop", "cancel"}
MORE = {"дальше", "следующий", "следующий трек", "скип", "пропусти"}
CONTEXT: dict[str, dict] = {}


def norm(value):
    value = str(value or "").casefold().replace("ё", "е").strip()
    value = re.sub(r"^акира[,:;\-]?\s*", "", value)
    value = re.sub(r"спотифа(?:й|я|е|и|ю)\b", "спотифай", value)
    value = re.sub(r"дискорд(?:а|у|ом|е)?\b", "дискорд", value)
    return re.sub(r"\s+", " ", value).strip(" .,!?:;")


def remember(session, kind, **data):
    CONTEXT[session] = {"kind": kind, **data}


def app_names(chunk):
    names = []
    for part in re.split(r"\s*(?:,|\bи\b|\bа также\b)\s*", chunk):
        part = re.sub(r"^(?:к|ко|в|на)\s+", "", part.strip())
        if part:
            names.append(APPS.get(part, part))
    return names


def parse_apps(text):
    pattern = r"(?:^|\s)(открой|запусти|закрой)\s+"
    matches = list(re.finditer(pattern, text))
    if not matches or matches[0].start() != 0:
        return None
    actions = []
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        chunk = re.sub(r"\s+(?:и|а затем|потом)\s*$", "", text[match.end():end].strip(" ,.!?:;"))
        targets = app_names(chunk)
        if not targets:
            return None
        actions.append(("open" if match.group(1) in {"открой", "запусти"} else "close", targets))
    return actions


def run_apps(actions):
    from capabilities.apps import open_target, close_target
    lines, done = [], []
    for operation, targets in actions:
        fn = open_target if operation == "open" else close_target
        with ThreadPoolExecutor(max_workers=len(targets)) as pool:
            futures = {pool.submit(fn, target): target for target in targets}
            results = {}
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
                ok.append(target); done.append(target)
            else:
                bad.append(f"{target}: {result.get('error') or 'не удалось'}")
        if ok:
            lines.append(("Открыл" if operation == "open" else "Закрыл") + ": " + ", ".join(ok) + ".")
        if bad:
            lines.append("Не удалось: " + "; ".join(bad))
    return " ".join(lines) or "Не удалось выполнить действие.", done


def volume_get():
    from capabilities.apps import _run
    result = _run("output volume of (get volume settings)")
    if result.returncode:
        raise RuntimeError("не удалось прочитать громкость")
    return max(0, min(100, int(result.stdout.strip())))


def volume_set(value):
    from capabilities.apps import _run
    value = max(0, min(100, int(value)))
    result = _run(f"set volume output volume {value}")
    if result.returncode:
        raise RuntimeError("не удалось изменить громкость")
    return value


def quick_chat(text):
    compact = re.sub(r"[!?.,]", "", text).strip()
    answers = {
        "привет": "Привет! Чем могу помочь?", "здравствуй": "Привет! Чем могу помочь?",
        "здравствуйте": "Привет! Чем могу помочь?", "хай": "Привет! Чем могу помочь?",
        "спасибо": "Пожалуйста.", "спс": "Пожалуйста.", "как дела": "Нормально. Готов работать.",
        "что ты умеешь": "Могу отвечать на вопросы, управлять приложениями, громкостью и Spotify, а также выполнять задачи на компьютере.",
    }
    return answers.get(compact)


def conversation(message):
    text = norm(message)
    quick = quick_chat(text)
    if quick:
        return quick
    from config import MODEL, create_groq_client
    client = create_groq_client()
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": "Ты Акира, мужской персональный ассистент. Отвечай по-русски, кратко и естественно. Не описывай внутренние инструменты и не выполняй компьютерные действия сам в этом режиме."},
            {"role": "user", "content": message},
        ],
        temperature=0.7,
        max_completion_tokens=500,
    )
    answer = response.choices[0].message.content
    return str(answer or "Не получил ответ.").strip()


def ask(message, session_id="desktop"):
    text = norm(message)
    if not text:
        return ""
    if text in STOP:
        CONTEXT.pop(session_id, None)
        return "Остановил."
    quick = quick_chat(text)
    if quick:
        return quick
    context = CONTEXT.get(session_id, {})
    if text in {"выключи", "поставь на паузу", "пауза"} and context.get("kind") == "spotify":
        from spotify_control import pause
        return pause()
    if text == "закрой" and context.get("kind") == "apps" and context.get("target"):
        return run_apps([("close", [context["target"]])])[0]
    if text in MORE and context.get("kind") == "spotify":
        from spotify_control import next_track
        return next_track()
    music = re.match(r"^(?:включи|поставь|сыграй)\s+(.+?)\s+(?:на|в)\s+спотифай$", text)
    if music:
        from spotify_control import play
        query = music.group(1).strip(); remember(session_id, "spotify", query=query)
        return play(query)
    if text in MORE:
        from spotify_control import next_track
        return next_track()
    if re.search(r"^(?:(?:какая|какой|сколько|текущая)\s+)?(?:сейчас\s+)?(?:громкость|уровень звука|звук)(?:\s+сейчас)?$", text):
        return f"Громкость: {volume_get()}%"
    match = re.search(r"(?:громкость|звук)(?:\s+на)?\s+(\d{1,3})(?:\s*%|\s*процент\w*)?$", text)
    if match:
        value = volume_set(match.group(1)); remember(session_id, "volume", delta=10)
        return f"Громкость: {value}%"
    if re.search(r"\b(?:громче|прибавь|увеличь)\b", text):
        value = volume_set(volume_get() + 10); remember(session_id, "volume", delta=10)
        return f"Громкость: {value}%"
    if re.search(r"\b(?:тише|убавь|уменьши)\b", text):
        value = volume_set(volume_get() - 10); remember(session_id, "volume", delta=-10)
        return f"Громкость: {value}%"
    if re.search(r"(?:выключи|убери)\s+(?:звук|громкость)", text):
        return f"Громкость: {volume_set(0)}%"
    actions = parse_apps(text)
    if actions:
        answer, done = run_apps(actions)
        if done:
            remember(session_id, "apps", target=done[-1])
        return answer
    return conversation(message)
