import json
import os

from groq import Groq
from memory import get_activity_totals, get_memory_snapshot


MODEL = "openai/gpt-oss-120b"

client = Groq(
    api_key=os.environ["GROQ_API_KEY"]
)


def check_proactive(days: int = 3) -> str:
    memory = get_memory_snapshot()

    goals = memory.get("goals", [])
    tasks = memory.get("tasks", [])
    events = memory.get("events", [])
    activity_totals = get_activity_totals(days)

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
