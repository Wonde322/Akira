import os
import subprocess
from urllib.parse import quote
import json
from groq import Groq


from tools import (
    open_app,
    close_app,
    set_volume,
    get_volume,
    mute_volume,
    get_running_apps
)

from analysis import analyze_period
from goal_analysis import analyze_goals
from proactive import check_proactive
from permissions import get_permission

from file_tools import find_files, delete_file

from memory import (
    add_goal,
    get_goals,
    add_task,
    get_tasks,
    complete_task,
    add_event,
    get_recent_events
)


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


TOOLS = [

    {
        "type": "function",
        "function": {
            "name": "open_youtube",
            "description": "Открывает Google Chrome и выполняет поиск на YouTube. Используй, когда пользователь просит открыть или найти что-либо на YouTube.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Что найти на YouTube."
                    }
                },
                "required": ["query"]
            }
        }
    },

    {
        "type": "function",
        "function": {
            "name": "play_spotify",
            "description": "Открывает поиск в установленном приложении Spotify. Используй, когда пользователь просит включить трек, исполнителя, альбом или музыку в Spotify.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Название трека, исполнителя, альбома или музыки."
                    }
                },
                "required": ["query"]
            }
        }
    },

    {
        "type": "function",
        "function": {
            "name": "check_proactive",
            "description": "Проверяет цели, задачи и активность пользователя и определяет, есть ли важный повод обратить его внимание.",
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "description": "Количество последних дней для проверки."
                    }
                },
                "required": ["days"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_goals",
            "description": "Сопоставляет цели, задачи и фактическую активность пользователя за указанный период.",
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "description": "Количество последних дней для анализа."
                    }
                },
                "required": ["days"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "find_files",
            "description": "Ищет файлы в домашней папке пользователя по части имени.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Имя или часть имени файла."
                    }
                },
                "required": ["name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delete_file",
            "description": "Перемещает указанный файл в Корзину macOS.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Полный путь к файлу."
                    }
                },
                "required": ["path"]
            }
        }
    },
        {
        "type": "function",
        "function": {
            "name": "analyze_period",
            "description": "Анализирует деятельность пользователя за указанное количество дней.",
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "description": "Количество последних дней для анализа."
                    }
                },
                "required": ["days"]
            }
        }
    },
        {
        "type": "function",
        "function": {
            "name": "open_app",
            "description": "Открывает приложение на Mac.",
            "parameters": {
                "type": "object",
                "properties": {
                    "app_name": {
                        "type": "string",
                        "description": "Название приложения."
                    }
                },
                "required": ["app_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "close_app",
            "description": "Закрывает приложение на Mac.",
            "parameters": {
                "type": "object",
                "properties": {
                    "app_name": {
                        "type": "string",
                        "description": "Название приложения."
                    }
                },
                "required": ["app_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "set_volume",
            "description": "Устанавливает громкость Mac от 0 до 100.",
            "parameters": {
                "type": "object",
                "properties": {
                    "level": {
                        "type": "integer",
                        "description": "Громкость от 0 до 100."
                    }
                },
                "required": ["level"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_volume",
            "description": "Узнаёт текущую громкость Mac.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "mute_volume",
            "description": "Выключает звук Mac.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_running_apps",
            "description": "Получает список запущенных приложений Mac.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "add_goal",
            "description": "Сохраняет долгосрочную цель пользователя.",
            "parameters": {
                "type": "object",
                "properties": {
                    "goal": {
                        "type": "string",
                        "description": "Формулировка цели."
                    }
                },
                "required": ["goal"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_goals",
            "description": "Показывает сохранённые цели пользователя.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Максимальное количество целей."
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "add_task",
            "description": "Добавляет новую задачу пользователя.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task": {
                        "type": "string",
                        "description": "Формулировка задачи."
                    },
                    "goal": {
                        "type": "string",
                        "description": "Цель, к которой относится задача, если она известна."
                    }
                },
                "required": ["task"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_tasks",
            "description": "Показывает активные задачи пользователя.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "complete_task",
            "description": "Отмечает задачу выполненной.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_text": {
                        "type": "string",
                        "description": "Название или часть названия задачи."
                    }
                },
                "required": ["task_text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "add_event",
            "description": "Записывает важное событие в историю пользователя.",
            "parameters": {
                "type": "object",
                "properties": {
                    "event": {
                        "type": "string",
                        "description": "Описание события."
                    }
                },
                "required": ["event"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_recent_events",
            "description": "Показывает последние события из истории пользователя.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Количество последних событий."
                    }
                },
                "required": ["limit"]
            }
        }
    }
]



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
            url
        ])

        return f"Открыл видео на YouTube: {query}"

    except Exception as e:
        return f"Не удалось открыть YouTube: {e}"


def play_spotify(query):
    """Передаёт управление Spotify рабочему spotify_control.py."""
    try:
        from spotify_control import play
        return play(query)
    except Exception as e:
        return f"Не удалось включить Spotify: {e}"


FUNCTIONS = {
    "open_youtube": open_youtube,
    "play_spotify": play_spotify,
    "analyze_period": analyze_period,
    "analyze_goals": analyze_goals,
    "check_proactive": check_proactive,
    "find_files": find_files,
    "delete_file": delete_file,
    "open_app": open_app,
    "close_app": close_app,
    "set_volume": set_volume,
    "get_volume": get_volume,
    "mute_volume": mute_volume,
    "get_running_apps": get_running_apps,
    "add_goal": add_goal,
    "get_goals": get_goals,
    "add_task": add_task,
    "get_tasks": get_tasks,
    "complete_task": complete_task,
    "add_event": add_event,
    "get_recent_events": get_recent_events,
}

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

    function = FUNCTIONS.get(function_name)

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
        "content": message
    })

    conversation = conversation[-MAX_HISTORY:]

    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT
        }
    ]

    messages.extend(conversation)

    response = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        tools=TOOLS,
        tool_choice="auto"
    )

    assistant_message = response.choices[0].message

    if not assistant_message.tool_calls:
        answer = assistant_message.content

        conversation.append({
            "role": "assistant",
            "content": answer
        })

        conversation = conversation[-MAX_HISTORY:]

        return answer

    messages.append(assistant_message)

    for tool_call in assistant_message.tool_calls:
        function_name = tool_call.function.name
        arguments = json.loads(tool_call.function.arguments)

        result = execute_tool(
            function_name,
            arguments
        )

        messages.append({
            "role": "tool",
            "tool_call_id": tool_call.id,
            "content": result
        })

    while True:
        final_response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto"
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
                arguments
            )

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": result
            })

    conversation.append({
        "role": "assistant",
        "content": answer
    })

    conversation = conversation[-MAX_HISTORY:]

    return answer
