"""Единый сервис LLM-анализа пользователя.

Все три инструмента (analyze_period, analyze_goals, check_proactive)
делегируют в общую способность analyze(focus, days). Данные для модели
собираются только под конкретный focus.
"""

import json

from config import MODEL, create_groq_client
from format import format_duration
from memory import get_activity_totals, get_events_for_period, get_memory_snapshot


client = None
FOCUSES = {"period", "goals", "proactive"}
MAX_ANALYSIS_DAYS = 3650


def _ensure_client():
    global client
    if client is None:
        client = create_groq_client()
    return client


def _validate_days(days):
    if isinstance(days, bool) or not isinstance(days, int) or days < 1:
        raise ValueError("days должен быть целым числом больше нуля")
    return min(days, MAX_ANALYSIS_DAYS)


def _format_activity_totals(days):
    totals = get_activity_totals(days)
    if not totals:
        return "Нет данных об активности."
    return "\n".join(
        f"- {app}: {format_duration(seconds)}"
        for app, seconds in sorted(totals.items(), key=lambda x: x[1], reverse=True)
    )


def _format_events(days):
    events = get_events_for_period(days)
    if not events:
        return "Нет событий за этот период."
    return "\n".join(event["time"] + " — " + event["text"] for event in events)


def _build_context(focus, days):
    """Собирает только те данные, которые нужны конкретному focus."""
    if focus == "period":
        return "СОБЫТИЯ:\n" + _format_events(days)

    memory = get_memory_snapshot()
    return "\n\n".join([
        "ЦЕЛИ:\n" + json.dumps(memory.get("goals", []), ensure_ascii=False, indent=2),
        "ЗАДАЧИ:\n" + json.dumps(memory.get("tasks", []), ensure_ascii=False, indent=2),
        "АКТИВНОСТЬ:\n" + _format_activity_totals(days),
    ])


def _period_prompt(days, context):
    return f"""Проанализируй деятельность пользователя за последние {days} дней.

{context}

Сделай краткий, но полезный анализ:
1. Чем пользователь в основном занимался.
2. Какие проекты или направления прослеживаются.
3. Что было сделано.
4. Какие задачи или направления выглядят заброшенными.
5. Есть ли очевидное расхождение между активностью и целями пользователя.

Не придумывай действий, которых нет в журнале. Если данных недостаточно для вывода — прямо скажи это. Отвечай на русском языке."""


def _goals_prompt(days, context):
    return f"""Ты анализируешь прогресс пользователя за последние {days} дней.

{context}

Сопоставь цели, задачи и фактическую активность. Определи актуальные цели,
связанные задачи, выполненные и висящие задачи, признаки работы над целями,
расхождения между целями и активностью и разумный следующий шаг.
Не придумывай данные. Не считай время в приложении автоматически продуктивной
работой. Если данных мало, прямо скажи об этом. Отвечай на русском, конкретно и кратко."""


def _proactive_prompt(days, context):
    return f"""Ты — проактивный персональный ассистент. Проверь ситуацию пользователя
за последние {days} дней.

{context}

Используй только INFO, ATTENTION или URGENT. Если важного повода нет, ответь
строго NO_ACTION. Иначе ответь:
LEVEL: INFO/ATTENTION/URGENT
REASON: кратко объясни причину
SUGGESTION: что имеет смысл сделать

Не ругай пользователя, не делай моральных оценок, не считай время в приложении
автоматически продуктивной работой и не придумывай отсутствующие данные. Если
данных мало — лучше NO_ACTION. Отвечай на русском."""


_PROMPTS = {"period": _period_prompt, "goals": _goals_prompt, "proactive": _proactive_prompt}


def analyze(focus: str, days: int) -> str:
    """Общая способность LLM-анализа пользователя."""
    if focus not in FOCUSES:
        return "Неизвестный фокус анализа: " + str(focus)

    try:
        days = _validate_days(days)
    except ValueError as error:
        return str(error)

    context = _build_context(focus, days)
    if focus == "period" and "Нет событий" in context:
        return "За этот период в журнале пока нет событий."

    try:
        response = _ensure_client().chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": _PROMPTS[focus](days, context)}],
        )
        content = response.choices[0].message.content
    except Exception as error:
        return "Не удалось выполнить анализ: " + str(error)

    if not isinstance(content, str) or not content.strip():
        return "Анализ не вернул содержательного ответа."
    return content.strip()


def analyze_period(days: int = 7) -> str:
    return analyze("period", days)


def analyze_goals(days: int = 7) -> str:
    return analyze("goals", days)


def check_proactive(days: int = 3) -> str:
    return analyze("proactive", days)
