import json
import os
from datetime import datetime, timedelta

from groq import Groq


MEMORY_FILE = "memory.json"
MODEL = "openai/gpt-oss-120b"

client = Groq(
    api_key=os.environ["GROQ_API_KEY"]
)


def load_memory():
    if not os.path.exists(MEMORY_FILE):
        return {}

    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as file:
            return json.load(file)
    except Exception:
        return {}


def check_proactive(days: int = 3) -> str:
    memory = load_memory()

    goals = memory.get("goals", [])
    tasks = memory.get("tasks", [])
    events = memory.get("events", [])
    activity = memory.get("activity", [])

    cutoff = datetime.now() - timedelta(days=days)

    recent_activity = []

    for session in activity:
        try:
            started = datetime.fromisoformat(session["started"])

            if started >= cutoff:
                recent_activity.append(session)

        except (KeyError, ValueError):
            continue

    activity_totals = {}

    for session in recent_activity:
        app = session.get("app", "Неизвестно")
        seconds = session.get("duration_seconds", 0)

        activity_totals[app] = (
            activity_totals.get(app, 0) + seconds
        )

    def format_time(seconds):
        minutes = int(seconds // 60)
        hours = minutes // 60
        minutes %= 60

        if hours:
            return f"{hours} ч {minutes} мин"

        return f"{minutes} мин"

    activity_text = "\n".join(
        f"- {app}: {format_time(seconds)}"
        for app, seconds in sorted(
            activity_totals.items(),
            key=lambda x: x[1],
            reverse=True
        )
    )

    if not activity_text:
        activity_text = "Нет данных об активности."

    tasks_text = json.dumps(
        tasks,
        ensure_ascii=False,
        indent=2
    )

    goals_text = json.dumps(
        goals,
        ensure_ascii=False,
        indent=2
    )

    prompt = f"""
Ты — проактивный персональный ассистент.

Проверь ситуацию пользователя за последние {days} дней.

ЦЕЛИ:
{goals_text}

ЗАДАЧИ:
{tasks_text}

АКТИВНОСТЬ:
{activity_text}

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

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ]
    )

    return response.choices[0].message.content


if __name__ == "__main__":
    print(check_proactive(3))
