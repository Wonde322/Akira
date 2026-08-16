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


def _ensure_client():
    global client

    if client is None:
        client = create_groq_client()

    return client


FOCUSES = {"period", "goals", "proactive"}


def _format_activity_totals(days):
    totals = get_activity_totals(days)

    if not totals:
        return "Нет данных об активности."

    return "\n".join(
        f"- {app}: {format_duration(seconds)}"
        for app, seconds in sorted(
            totals.items(),
            key=lambda x: x[1],
            reverse=True,
        )
    )


def _format_events(days):
    events = get_events_for_period(days)

    if not events:
        return "Нет событий за этот период."

    return "\n".join(
        event["time"] + " — " + event["text"]
        for event in events
    )


def _build_context(focus, days):
    """Собирает только те данные, которые нужны конкретному focus."""
    if focus == "period":
        return "СОБЫТИЯ:\n" + _format_events(days)

    memory = get_memory_snapshot()

    goals = memory.get("goals", [])
    tasks = memory.get("tasks", [])

    return "\n\n".join([
        "ЦЕЛИ:\n" + json.dumps(goals, ensure_ascii=False, indent=2),
        "ЗАДАЧИ:\n" + json.dumps(tasks, ensure_ascii=False, indent=2),
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

Не придумывай действий, которых нет в журнале.
Если данных недостаточно для какого-либо вывода — прямо скажи это.

Отвечай на русском языке.
"""


def _goals_prompt(days, context):
    return f"""Ты анализируешь прогресс пользователя за последние {days} дней.

{context}

Сопоставь цели, задачи и фактическую активность.

Определи:

1. Какие цели сейчас наиболее актуальны.
2. Какие задачи относятся к этим целям.
3. Какие задачи выполнены, а какие ещё висят.
4. Какая активность действительно похожа на работу над целями.
5. Есть ли заметное расхождение между заявленными целями и фактической активностью.
6. Что имеет смысл сделать дальше.

Не придумывай данные.
Не считай время в приложении автоматически временем продуктивной работы.
Например, Chrome может использоваться для работы, развлечений или чего угодно ещё.

Если данных мало, прямо скажи об этом.

Отвечай на русском языке.
Будь конкретным и кратким.
"""


def _proactive_prompt(days, context):
    return f"""Ты — проактивный персональный ассистент.

Проверь ситуацию пользователя за последние {days} дней.

{context}

Определи, есть ли действительно важный повод обратить внимание пользователя.

Используй только три уровня:

INFO
Интересный факт, который не требует действия.

ATTENTION
Есть заметная проблема, отклонение от цели или полезный повод что-то сделать.

URGENT
Есть действительно важная ситуация, которую желательно не откладывать.

Если повода нет, ответь строго:
NO_ACTION

Если повод есть, ответь в формате:

LEVEL: INFO/ATTENTION/URGENT
REASON: кратко объясни причину
SUGGESTION: что пользователю имеет смысл сделать

Не ругай пользователя и не делай моральных оценок.
Не считай время в приложении автоматически продуктивной работой.
Не придумывай отсутствующие данные.
Если данных мало — лучше ответить NO_ACTION.

Отвечай на русском.
"""


_PROMPTS = {
    "period": _period_prompt,
    "goals": _goals_prompt,
    "proactive": _proactive_prompt,
}


def analyze(focus: str, days: int) -> str:
    """Общая способность LLM-анализа пользователя."""
    if focus not in FOCUSES:
        return "Неизвестный фокус анализа: " + focus

    context = _build_context(focus, days)

    if focus == "period" and "Нет событий" in context:
        return "За этот период в журнале пока нет событий."

    prompt = _PROMPTS[focus](days, context)

    response = _ensure_client().chat.completions.create(
        model=MODEL,
        messages=[
            {
                "role": "user",
                "content": prompt,
            }
        ],
    )

    return response.choices[0].message.content


def analyze_period(days: int = 7) -> str:
    return analyze("period", days)


def analyze_goals(days: int = 7) -> str:
    return analyze("goals", days)


def check_proactive(days: int = 3) -> str:
    return analyze("proactive", days)