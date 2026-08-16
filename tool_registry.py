"""Declarative registry for the tools available to Akira's brain."""

from dataclasses import dataclass
from importlib import import_module

from skills.loader import load_skill_tools


PERMISSION_LEVELS = {"auto", "confirm", "blocked"}


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    parameters: dict
    implementation_module: str
    implementation_name: str
    permission_policy: str

    def schema(self):
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def implementation(self):
        module = import_module(self.implementation_module)
        return getattr(module, self.implementation_name)


def _parameters(properties, required=None):
    parameters = {
        "type": "object",
        "properties": properties,
    }

    if required is not None:
        parameters["required"] = required

    return parameters


TOOL_REGISTRY = (
    ToolDefinition(
        "discover_capability",
        "Ищет capability во всём registry, включая инструменты, которые "
        "текущий relevance-router не показал. Используй, если для задачи "
        "нужна конкретная возможность, которой нет среди текущих tools.",
        _parameters({
            "query": {
                "type": "string",
                "description": "Что именно должна уметь нужная capability.",
            },
            "limit": {
                "type": "integer",
                "description": "Максимум найденных capabilities (1-12).",
            },
        }, ["query"]),
        "capabilities.discovery",
        "discover_capability",
        "auto",
    ),
    ToolDefinition(
        "plan_task",
        "Создаёт внутренний план выполнения сложной задачи.",
        _parameters({
            "steps": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Последовательность конкретных проверяемых шагов.",
            },
        }, ["steps"]),
        "capabilities.task", "plan_task", "auto",
    ),
    ToolDefinition(
        "update_task_plan",
        "Перестраивает внутренний план после ошибки или изменения состояния.",
        _parameters({
            "steps": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Новый последовательный план.",
            },
        }, ["steps"]),
        "capabilities.task", "update_task_plan", "auto",
    ),
    ToolDefinition(
        "complete_plan_step",
        "Подтверждает, что текущий шаг внутреннего плана действительно выполнен. "
        "Используй только после фактической проверки результата.",
        _parameters({
            "evidence": {
                "type": "string",
                "description": "Краткое фактическое подтверждение результата.",
            },
        }),
        "capabilities.task", "complete_plan_step", "auto",
    ),
    ToolDefinition(
        "fail_plan_step",
        "Фиксирует, что текущий шаг плана не выполнен, с причиной для последующего replanning.",
        _parameters({
            "reason": {
                "type": "string",
                "description": "Причина, по которой текущий шаг не выполнен.",
            },
        }),
        "capabilities.task", "fail_plan_step", "auto",
    ),
    ToolDefinition(
        "open_youtube",
        "Открывает Google Chrome и выполняет поиск на YouTube. Используй, когда пользователь просит открыть или найти что-либо на YouTube.",
        _parameters({"query": {"type": "string", "description": "Что найти на YouTube."}}, ["query"]),
        "youtube", "open_youtube", "auto",
    ),
    ToolDefinition(
        "play_spotify",
        "Открывает поиск в установленном приложении Spotify. Используй, когда пользователь просит включить трек, исполнителя, альбом или музыку в Spotify.",
        _parameters({"query": {"type": "string", "description": "Название трека, исполнителя, альбома или музыки."}}, ["query"]),
        "spotify_control", "play", "auto",
    ),
    ToolDefinition(
        "check_proactive",
        "Проверяет цели, задачи и активность пользователя и определяет, есть ли важный повод обратить его внимание.",
        _parameters({"days": {"type": "integer", "description": "Количество последних дней для проверки."}}, ["days"]),
        "analysis", "check_proactive", "confirm",
    ),
    ToolDefinition(
        "analyze_goals",
        "Сопоставляет цели, задачи и фактическую активность пользователя за указанный период.",
        _parameters({"days": {"type": "integer", "description": "Количество последних дней для анализа."}}, ["days"]),
        "analysis", "analyze_goals", "confirm",
    ),
    ToolDefinition(
        "analyze_period",
        "Анализирует деятельность пользователя за указанное количество дней.",
        _parameters({"days": {"type": "integer", "description": "Количество последних дней для анализа."}}, ["days"]),
        "analysis", "analyze_period", "auto",
    ),
    ToolDefinition(
        "set_volume",
        "Устанавливает громкость Mac от 0 до 100.",
        _parameters({"level": {"type": "integer", "description": "Громкость от 0 до 100."}}, ["level"]),
        "tools", "set_volume", "confirm",
    ),
    ToolDefinition(
        "get_volume",
        "Узнаёт текущую громкость Mac.",
        _parameters({}),
        "tools", "get_volume", "auto",
    ),
    ToolDefinition(
        "mute_volume",
        "Выключает звук Mac.",
        _parameters({}),
        "tools", "mute_volume", "confirm",
    ),
    ToolDefinition(
        "get_running_apps",
        "Получает список запущенных приложений Mac.",
        _parameters({}),
        "tools", "get_running_apps", "auto",
    ),
    ToolDefinition(
        "remember_memory",
        "Сохраняет долговременную память Akira. Используй для устойчивых "
        "фактов, предпочтений, важных эпизодов и успешных процедур.",
        _parameters({
            "content": {
                "type": "string",
                "description": "Что нужно сохранить.",
            },
            "kind": {
                "type": "string",
                "enum": [
                    "fact",
                    "preference",
                    "episode",
                    "procedure",
                ],
                "description": "Тип долговременной памяти.",
            },
            "key": {
                "type": "string",
                "description": "Короткий ключ/название памяти.",
            },
            "source": {
                "type": "string",
                "description": "Источник памяти, например user или agent.",
            },
            "importance": {
                "type": "number",
                "description": "Важность от 0 до 1.",
            },
        }, ["content"]),
        "memory", "remember_memory", "auto",
    ),
    ToolDefinition(
        "recall_memory",
        "Ищет релевантную долговременную память пользователя по смыслу запроса.",
        _parameters({
            "query": {
                "type": "string",
                "description": "Что нужно вспомнить.",
            },
            "limit": {
                "type": "integer",
                "description": "Максимум результатов, 1-20.",
            },
        }, ["query"]),
        "memory", "recall_memory", "auto",
    ),
    ToolDefinition(
        "add_goal",
        "Сохраняет долгосрочную цель пользователя.",
        _parameters({"goal": {"type": "string", "description": "Формулировка цели."}}, ["goal"]),
        "memory", "add_goal", "auto",
    ),
    ToolDefinition(
        "get_goals",
        "Показывает сохранённые цели пользователя.",
        _parameters({"limit": {"type": "integer", "description": "Максимальное количество целей."}}),
        "memory", "get_goals", "auto",
    ),
    ToolDefinition(
        "add_task",
        "Добавляет новую задачу пользователя.",
        _parameters({
            "task": {"type": "string", "description": "Формулировка задачи."},
            "goal": {"type": "string", "description": "Цель, к которой относится задача, если она известна."},
        }, ["task"]),
        "memory", "add_task", "auto",
    ),
    ToolDefinition(
        "get_tasks",
        "Показывает активные задачи пользователя.",
        _parameters({}),
        "memory", "get_tasks", "auto",
    ),
    ToolDefinition(
        "complete_task",
        "Отмечает задачу выполненной.",
        _parameters({"task_text": {"type": "string", "description": "Название или часть названия задачи."}}, ["task_text"]),
        "memory", "complete_task", "auto",
    ),
    ToolDefinition(
        "add_event",
        "Записывает важное событие в историю пользователя.",
        _parameters({"event": {"type": "string", "description": "Описание события."}}, ["event"]),
        "memory", "add_event", "auto",
    ),
    ToolDefinition(
        "get_recent_events",
        "Показывает последние события из истории пользователя.",
        _parameters({"limit": {"type": "integer", "description": "Количество последних событий."}}, ["limit"]),
        "memory", "get_recent_events", "auto",
    ),
    ToolDefinition(
        "observe",
        "Делает снимок экрана macOS и возвращает его путь, размеры экрана и размер файла. При interpret=True дополнительно отправляет снимок модели для описания происходящего. observe описывает состояние экрана, но не предлагает координаты для клика.",
        _parameters({
            "interpret": {"type": "boolean", "description": "True — отправить снимок модели для описания."},
            "description_prompt": {"type": "string", "description": "Кастомная инструкция для интерпретации снимка."},
        }),
        "capabilities.observe", "observe", "auto",
    ),
    ToolDefinition(
        "screen_size",
        "Возвращает размеры основного экрана macOS.",
        _parameters({}),
        "capabilities.observe", "screen_size", "auto",
    ),
    ToolDefinition(
        "open",
        "Универсально открывает приложение, URL или файл на Mac: open(target='Google Chrome'), open(target='https://youtube.com'), open(target='/path').",
        _parameters({"target": {"type": "string", "description": "Имя приложения, URL или абсолютный путь."}}, ["target"]),
        "capabilities.apps", "open_target", "auto",
    ),
    ToolDefinition(
        "close",
        "Закрывает приложение на Mac по имени или пути к .app.",
        _parameters({"target": {"type": "string", "description": "Имя приложения или путь к .app."}}, ["target"]),
        "capabilities.apps", "close_target", "auto",
    ),
    ToolDefinition(
        "find",
        "Ищет файлы и каталоги внутри домашней папки по части имени.",
        _parameters({
            "name": {"type": "string", "description": "Имя или часть имени."},
            "directory": {"type": "string", "description": "Абсолютный путь для поиска (по умолчанию домашняя папка)."},
            "limit": {"type": "integer", "description": "Максимум результатов (до 50)."},
            "kind": {"type": "string", "enum": ["file", "dir"], "description": "Фильтр: только файлы или только каталоги."},
        }, ["name"]),
        "capabilities.filesystem", "find", "auto",
    ),
    ToolDefinition(
        "read",
        "Читает текстовый файл (UTF-8) внутри домашней папки.",
        _parameters({
            "path": {"type": "string", "description": "Абсолютный путь к файлу."},
            "max_bytes": {"type": "integer", "description": "Ограничение на количество читаемых байт."},
        }, ["path"]),
        "capabilities.filesystem", "read", "auto",
    ),
    ToolDefinition(
        "write",
        "Записывает текст в файл, создавая родительские каталоги.",
        _parameters({
            "path": {"type": "string", "description": "Абсолютный путь к файлу."},
            "content": {"type": "string", "description": "Текст для записи."},
            "append": {"type": "boolean", "description": "True — дописать в конец, False — перезаписать."},
        }, ["path", "content"]),
        "capabilities.filesystem", "write", "confirm",
    ),
    ToolDefinition(
        "create",
        "Создаёт новый файл или каталог внутри домашней папки.",
        _parameters({
            "path": {"type": "string", "description": "Абсолютный путь."},
            "kind": {"type": "string", "enum": ["file", "dir"], "description": "Тип создаваемого объекта."},
            "content": {"type": "string", "description": "Содержимое для файла."},
            "overwrite": {"type": "boolean", "description": "True — перезаписать существующий файл."},
        }, ["path"]),
        "capabilities.filesystem", "create", "confirm",
    ),
    ToolDefinition(
        "move",
        "Перемещает файл или каталог в новый путь внутри домашней папки.",
        _parameters({
            "source": {"type": "string", "description": "Абсолютный путь источника."},
            "destination": {"type": "string", "description": "Абсолютный путь назначения (файл или каталог)."},
        }, ["source", "destination"]),
        "capabilities.filesystem", "move", "confirm",
    ),
    ToolDefinition(
        "copy",
        "Копирует файл или каталог в новый путь внутри домашней папки.",
        _parameters({
            "source": {"type": "string", "description": "Абсолютный путь источника."},
            "destination": {"type": "string", "description": "Абсолютный путь назначения."},
        }, ["source", "destination"]),
        "capabilities.filesystem", "copy", "confirm",
    ),
    ToolDefinition(
        "rename",
        "Переименовывает файл или каталог (только новое имя в том же каталоге).",
        _parameters({
            "path": {"type": "string", "description": "Абсолютный путь."},
            "new_name": {"type": "string", "description": "Новое имя без разделителей пути."},
        }, ["path", "new_name"]),
        "capabilities.filesystem", "rename", "confirm",
    ),
    ToolDefinition(
        "delete",
        "Перемещает файл или каталог в Корзину macOS (безвозвратно не удаляет).",
        _parameters({"path": {"type": "string", "description": "Абсолютный путь."}}, ["path"]),
        "capabilities.filesystem", "delete", "confirm",
    ),
    ToolDefinition(
        "shell",
        "Выполняет команду в оболочке macOS с таймаутом. Возвращает код возврата, stdout и stderr.",
        _parameters({
            "command": {"type": "string", "description": "Команда для выполнения."},
            "timeout": {"type": "integer", "description": "Таймаут в секундах (1-120)."},
            "cwd": {"type": "string", "description": "Рабочий каталог (абсолютный путь внутри домашней папки)."},
        }, ["command"]),
        "capabilities.shell", "shell", "confirm",
    ),
    ToolDefinition(
        "wait",
        "Пауза на указанное число секунд (до 60).",
        _parameters({
            "seconds": {"type": "number", "description": "Секунды ожидания."},
            "reason": {"type": "string", "description": "Причина ожидания."},
        }, ["seconds"]),
        "capabilities.wait", "wait", "auto",
    ),
    ToolDefinition(
        "key",
        "Отправляет клавиатурную комбинацию на Mac, например 'command+shift+4' или 'return'.",
        _parameters({"keys": {"type": "string", "description": "Комбинация клавиш через + или пробел."}}, ["keys"]),
        "capabilities.key", "key", "auto",
    ),
    ToolDefinition(
        "select",
        "Универсальный выбор элемента в точке экрана: наводит указатель на (x, y) и делает один левый клик. Композиция move+click без поиска элементов.",
        _parameters({
            "x": {"type": "number", "description": "Координата x."},
            "y": {"type": "number", "description": "Координата y."},
        }, ["x", "y"]),
        "capabilities.gui", "select", "auto",
    ),
    ToolDefinition(
        "click",
        "Нажимает кнопку мыши в точке экрана (x, y).",
        _parameters({
            "x": {"type": "number", "description": "Координата x."},
            "y": {"type": "number", "description": "Координата y."},
            "button": {"type": "string", "enum": ["left", "right", "middle"], "description": "Кнопка мыши."},
            "clicks": {"type": "integer", "description": "Количество кликов (1-10)."},
        }, ["x", "y"]),
        "capabilities.gui", "click", "auto",
    ),
    ToolDefinition(
        "type",
        "Печатает текст в указанное приложение (target). Перед вводом активирует target и проверяет, что он стал frontmost; только после этого отправляет keystroke. target обычно равен frontmost_app из последнего observe. Без target текст не печатается (target_required).",
        _parameters({
            "text": {"type": "string", "description": "Текст для ввода."},
            "target": {"type": "string", "description": "Имя приложения, в которое печатать (например, frontmost_app из последнего observe)."},
        }, ["text"]),
        "capabilities.gui", "type_text", "auto",
    ),
    ToolDefinition(
        "scroll",
        "Прокручивает содержимое под курсором или в указанной точке.",
        _parameters({
            "x": {"type": "number", "description": "Координата x (необязательно)."},
            "y": {"type": "number", "description": "Координата y (необязательно)."},
            "direction": {"type": "string", "enum": ["up", "down", "left", "right"], "description": "Направление прокрутки."},
            "amount": {"type": "integer", "description": "Величина прокрутки (1-50)."},
        }),
        "capabilities.gui", "scroll", "auto",
    ),
    ToolDefinition(
        "drag",
        "Перетаскивает объект из точки (x1, y1) в точку (x2, y2).",
        _parameters({
            "x1": {"type": "number", "description": "Стартовый x."},
            "y1": {"type": "number", "description": "Стартовый y."},
            "x2": {"type": "number", "description": "Конечный x."},
            "y2": {"type": "number", "description": "Конечный y."},
            "duration": {"type": "number", "description": "Длительность в секундах (0-5)."},
            "button": {"type": "string", "enum": ["left", "right", "middle"], "description": "Кнопка мыши."},
        }, ["x1", "y1", "x2", "y2"]),
        "capabilities.gui", "drag", "auto",
    ),
    ToolDefinition(
        "verify_goal",
        "Проверяет, достигнута ли цель текущей задачи после свежего observe. "
        "Используй verified только когда фактическое состояние подтверждает цель. "
        "Используй uncertain, если доказательств недостаточно, и failed если "
        "цель явно не достигнута.",
        _parameters({
            "status": {
                "type": "string",
                "enum": ["verified", "failed", "uncertain"],
                "description": "Статус проверки цели.",
            },
            "evidence": {
                "type": "string",
                "description": "Конкретное фактическое evidence из последнего состояния.",
            },
        }, ["status", "evidence"]),
        "capabilities.task",
        "verify_goal",
        "auto",
    ),
    ToolDefinition(
        "finish_task",
        "Завершает задачу computer-use и сообщает итог. Вызывай, когда цель достигнута, экран соответствует ожиданию или дальше действовать невозможно.",
        _parameters({"result": {"type": "string", "description": "Итог/статус завершения задачи."}}, ["result"]),
        "capabilities.task", "finish_task", "auto",
    ),
)



# ------------------------------------------------------------
# External skills
# ------------------------------------------------------------
#
# Core tools stay declarative and local to this file.
# Skills extend the registry without requiring changes to brain.py.
#
# A broken optional skill is ignored rather than preventing Akira from
# starting. The error can be inspected through get_skill_load_errors().
#
SKILL_TOOLS, SKILL_LOAD_ERRORS = load_skill_tools()

# Skills являются расширениями, а не заменой core.
# Если имя уже существует — core tool имеет приоритет.
_core_names = {tool.name for tool in TOOL_REGISTRY}
SKILL_COLLISIONS = []
_SKILL_UNIQUE = []

for _skill_tool in SKILL_TOOLS:
    if _skill_tool.name in _core_names:
        SKILL_COLLISIONS.append({
            "name": _skill_tool.name,
            "source": _skill_tool.implementation_module,
            "reason": "core_tool_wins",
        })
        continue

    if any(tool.name == _skill_tool.name for tool in _SKILL_UNIQUE):
        SKILL_COLLISIONS.append({
            "name": _skill_tool.name,
            "source": _skill_tool.implementation_module,
            "reason": "duplicate_skill",
        })
        continue

    _SKILL_UNIQUE.append(_skill_tool)

TOOL_REGISTRY = tuple(TOOL_REGISTRY) + tuple(_SKILL_UNIQUE)


def get_skill_load_errors():
    return list(SKILL_LOAD_ERRORS)


def get_skill_collisions():
    return list(SKILL_COLLISIONS)


def _validate_registry():
    names = [tool.name for tool in TOOL_REGISTRY]

    if len(names) != len(set(names)):
        raise ValueError("В registry есть повторяющиеся имена tools.")

    if any(tool.permission_policy not in PERMISSION_LEVELS for tool in TOOL_REGISTRY):
        raise ValueError("В registry есть недопустимая permission policy.")


_validate_registry()


def get_tool_schemas():
    return [tool.schema() for tool in TOOL_REGISTRY]


def get_tool_definition(name):
    for tool in TOOL_REGISTRY:
        if tool.name == name:
            return tool

    return None


def get_tool_implementation(name):
    tool = get_tool_definition(name)
    return tool.implementation() if tool else None


def get_default_tool_permissions():
    return {tool.name: tool.permission_policy for tool in TOOL_REGISTRY}

# === AKIRA BROWSER 2.0 TOOLS ===
#
# Browser is a separate capability layer.
# Existing application-specific tools remain untouched.

TOOL_REGISTRY = TOOL_REGISTRY + (
    ToolDefinition(
        "browser_start",
        "Запускает отдельную Chrome-сессию Akira с Chrome DevTools Protocol.",
        _parameters({}),
        "capabilities.browser",
        "browser_start",
        "auto",
    ),
    ToolDefinition(
        "browser_tabs",
        "Показывает вкладки в Chrome-сессии Akira.",
        _parameters({}),
        "capabilities.browser",
        "browser_tabs",
        "auto",
    ),
    ToolDefinition(
        "browser_current",
        "Возвращает текущую вкладку Chrome-сессии Akira.",
        _parameters({}),
        "capabilities.browser",
        "browser_current",
        "auto",
    ),
    ToolDefinition(
        "browser_navigate",
        "Переходит на URL в Chrome через CDP.",
        _parameters({
            "url": {
                "type": "string",
                "description": "URL страницы.",
            },
            "tab_id": {
                "type": "string",
                "description": "ID вкладки. Если не указан — текущая вкладка.",
            },
        }, ["url"]),
        "capabilities.browser",
        "browser_navigate",
        "auto",
    ),
    ToolDefinition(
        "browser_back",
        "Возвращает выбранную вкладку Chrome назад по истории.",
        _parameters({
            "tab_id": {
                "type": "string",
                "description": "ID вкладки.",
            },
        }),
        "capabilities.browser",
        "browser_back",
        "auto",
    ),
    ToolDefinition(
        "browser_reload",
        "Перезагружает выбранную вкладку Chrome.",
        _parameters({
            "tab_id": {
                "type": "string",
                "description": "ID вкладки.",
            },
        }),
        "capabilities.browser",
        "browser_reload",
        "auto",
    ),
    ToolDefinition(
        "browser_execute",
        "Выполняет JavaScript в DOM выбранной вкладки Chrome. Используй для чтения или управления DOM, когда browser/GUI-маршрут подходит лучше.",
        _parameters({
            "expression": {
                "type": "string",
                "description": "JavaScript expression.",
            },
            "tab_id": {
                "type": "string",
                "description": "ID вкладки.",
            },
        }, ["expression"]),
        "capabilities.browser",
        "browser_execute",
        "auto",
    ),
)

# === AKIRA BACKGROUND TASK RUNTIME ===
#
# Background tasks run through the same brain/tool/permission
# architecture as foreground requests.

TOOL_REGISTRY = TOOL_REGISTRY + (
    ToolDefinition(
        "background_task_start",
        "Запускает автономную задачу Akira в фоне. Используй, когда задача может выполняться независимо от текущего диалога и пользователь не должен ждать её завершения.",
        _parameters({
            "goal": {
                "type": "string",
                "description": "Полная цель фоновой задачи.",
            },
        }, ["goal"]),
        "task_runtime",
        "background_task_start",
        "auto",
    ),
    ToolDefinition(
        "background_task_status",
        "Показывает состояние конкретной фоновой задачи.",
        _parameters({
            "task_id": {
                "type": "string",
                "description": "ID фоновой задачи.",
            },
        }, ["task_id"]),
        "task_runtime",
        "background_task_status",
        "auto",
    ),
    ToolDefinition(
        "background_tasks",
        "Показывает последние фоновые задачи Akira.",
        _parameters({
            "limit": {
                "type": "integer",
                "description": "Количество задач, максимум 50.",
            },
        }),
        "task_runtime",
        "background_tasks",
        "auto",
    ),
    ToolDefinition(
        "background_task_result",
        "Возвращает результат фоновой задачи, если она уже завершилась.",
        _parameters({
            "task_id": {
                "type": "string",
                "description": "ID фоновой задачи.",
            },
        }, ["task_id"]),
        "task_runtime",
        "background_task_result",
        "auto",
    ),
)
