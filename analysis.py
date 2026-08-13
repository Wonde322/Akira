import os

from groq import Groq
from memory import get_events_for_period


MODEL = "openai/gpt-oss-120b"

client = Groq(
    api_key=os.environ["GROQ_API_KEY"]
)


def analyze_period(days: int = 7) -> str:
    """Анализирует деятельность пользователя за последние N дней."""

    events = get_events_for_period(days)

    if not events:
        return "За этот период в журнале пока нет событий."

    events_text = "\n".join(
        event["time"] + " — " + event["text"]
        for event in events
    )

    prompt = f"""
Проанализируй деятельность пользователя за последние {days} дней.

Вот журнал событий:

{events_text}

Сделай краткий, но полезный анализ:

1. Чем пользователь в основном занимался.
2. Какие проекты или направления прослеживаются.
3. Что было сделано.
4. Какие задачи или направления выглядят заброшенными.
5. Есть ли очевидное расхождение между активностью и целями пользователя.

Не придумывай действия, которых нет в журнале.
Если данных недостаточно для какого-либо вывода — прямо скажи это.

Отвечай на русском языке.
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
