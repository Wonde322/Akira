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


def analyze_goals(days: int = 7) -> str:
    memory = load_memory()

    goals = memory.get("goals", [])
    tasks = memory.get("tasks", [])
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

    goals_text = json.dumps(
        goals,
        ensure_ascii=False,
        indent=2
    )

    tasks_text = json.dumps(
        tasks,
        ensure_ascii=False,
        indent=2
    )

    activity_text = "\n".join(
        f"- {app}: {format_time(seconds)}"
        for app, seconds in sorted(
            activity_totals.items(),
            key=lambda x: x[1],
            reverse=True
        )
    )

    if not activity_text:
        activity_text = "Активность за этот период пока отсутствует."

    prompt = f"""
Ты анализируешь прогресс пользователя за последние {days} дней.

ЦЕЛИ:
{goals_text}

ЗАДАЧИ:
{tasks_text}

ФАКТИЧЕСКАЯ АКТИВНОСТЬ:
{activity_text}

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
    print(analyze_goals(7))
