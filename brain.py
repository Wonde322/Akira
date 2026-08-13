import json
import os

from groq import Groq

from permissions import get_permission
from tool_registry import get_tool_implementation, get_tool_schemas


MODEL = "openai/gpt-oss-120b"
MAX_HISTORY = 12

client = Groq(
    api_key=os.environ["GROQ_API_KEY"]
)


SYSTEM_PROMPT = """
Ты — Акира, персональный ассистент пользователя.

Обращайся к себе в мужском роде.
Отвечай на русском языке.
Будь кратким и естественным.

У тебя есть доступ к Mac и долговременной памяти пользователя.

Используй память, когда пользователь:
- просит что-то запомнить;
- сообщает новую цель;
- добавляет задачу;
- спрашивает о своих целях;
- спрашивает о задачах;
- отмечает задачу выполненной;
- спрашивает о недавних событиях.

Если пользователь просит что-то сохранить, обязательно используй соответствующий инструмент.
Не говори, что информация сохранена, если инструмент не был вызван успешно.

Если пользователь спрашивает, чем он занимался за определённый период,
используй инструмент analyze_period.

Ты можешь управлять Mac через доступные инструменты.

Не закрывай приложения без явной просьбы пользователя.

Учитывай предыдущие сообщения в разговоре.
Если пользователь использует слова вроде «его», «её», «это», «там», «сделай так же»
или другие контекстные ссылки, определяй их значение по истории разговора.

Отвечай кратко и естественно.
"""


def open_youtube(query):
    """Ищет первое подходящее видео на YouTube и открывает его в Chrome."""
    import subprocess

    try:
        result = subprocess.run(
            [
                os.path.expanduser("~/Akira/.venv/bin/yt-dlp"),
                f"ytsearch1:{query}",
                "--print", "webpage_url",
                "--skip-download",
                "--no-warnings",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        urls = [
            line.strip()
            for line in result.stdout.splitlines()
            if line.strip().startswith("https://www.youtube.com/watch")
        ]

        if not urls:
            return f"Не удалось найти видео на YouTube: {query}"

        url = urls[0]

        subprocess.run([
            "open",
            "-a",
            "Google Chrome",
            url,
        ])

        return f"Открыл видео на YouTube: {query}"

    except Exception as error:
        return f"Не удалось открыть YouTube: {error}"


def play_spotify(query):
    """Передаёт управление Spotify рабочему spotify_control.py."""
    try:
        from spotify_control import play
        return play(query)
    except Exception as error:
        return f"Не удалось включить Spotify: {error}"


TOOLS = get_tool_schemas()


def execute_tool(function_name, arguments):
    permission = get_permission(function_name)

    if permission == "blocked":
        return "Инструмент заблокирован настройками разрешений."

    if permission == "confirm":
        print()
        print("Акира хочет выполнить действие:")
        print("Инструмент:", function_name)
        print("Параметры:", arguments)

        answer = input("Разрешить? [да/нет]: ").strip().lower()

        if answer not in ["да", "д", "yes", "y"]:
            return "Пользователь не разрешил выполнение действия."

    function = get_tool_implementation(function_name)

    if function is None:
        return "Неизвестный инструмент."

    try:
        return function(**arguments)

    except Exception as error:
        return "Ошибка выполнения инструмента: " + str(error)


conversation = []


def ask(message):
    global conversation

    conversation.append({
        "role": "user",
        "content": message,
    })

    conversation = conversation[-MAX_HISTORY:]

    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT,
        }
    ]

    messages.extend(conversation)

    response = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        tools=TOOLS,
        tool_choice="auto",
    )

    assistant_message = response.choices[0].message

    if not assistant_message.tool_calls:
        answer = assistant_message.content

        conversation.append({
            "role": "assistant",
            "content": answer,
        })

        conversation = conversation[-MAX_HISTORY:]

        return answer

    messages.append(assistant_message)

    for tool_call in assistant_message.tool_calls:
        function_name = tool_call.function.name
        arguments = json.loads(tool_call.function.arguments)

        result = execute_tool(
            function_name,
            arguments,
        )

        messages.append({
            "role": "tool",
            "tool_call_id": tool_call.id,
            "content": result,
        })

    while True:
        final_response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
        )

        next_message = final_response.choices[0].message

        if not next_message.tool_calls:
            answer = next_message.content
            break

        messages.append(next_message)

        for tool_call in next_message.tool_calls:
            function_name = tool_call.function.name
            arguments = json.loads(tool_call.function.arguments)

            result = execute_tool(
                function_name,
                arguments,
            )

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": result,
            })

    conversation.append({
        "role": "assistant",
        "content": answer,
    })

    conversation = conversation[-MAX_HISTORY:]

    return answer
