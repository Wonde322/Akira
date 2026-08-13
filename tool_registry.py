"""Declarative registry for the tools available to Akira's brain."""

from dataclasses import dataclass
from importlib import import_module


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
        "open_youtube",
        "Открывает Google Chrome и выполняет поиск на YouTube. Используй, когда пользователь просит открыть или найти что-либо на YouTube.",
        _parameters({"query": {"type": "string", "description": "Что найти на YouTube."}}, ["query"]),
        "brain", "open_youtube", "confirm",
    ),
    ToolDefinition(
        "play_spotify",
        "Открывает поиск в установленном приложении Spotify. Используй, когда пользователь просит включить трек, исполнителя, альбом или музыку в Spotify.",
        _parameters({"query": {"type": "string", "description": "Название трека, исполнителя, альбома или музыки."}}, ["query"]),
        "brain", "play_spotify", "confirm",
    ),
    ToolDefinition(
        "check_proactive",
        "Проверяет цели, задачи и активность пользователя и определяет, есть ли важный повод обратить его внимание.",
        _parameters({"days": {"type": "integer", "description": "Количество последних дней для проверки."}}, ["days"]),
        "proactive", "check_proactive", "confirm",
    ),
    ToolDefinition(
        "analyze_goals",
        "Сопоставляет цели, задачи и фактическую активность пользователя за указанный период.",
        _parameters({"days": {"type": "integer", "description": "Количество последних дней для анализа."}}, ["days"]),
        "goal_analysis", "analyze_goals", "confirm",
    ),
    ToolDefinition(
        "find_files",
        "Ищет файлы в домашней папке пользователя по части имени.",
        _parameters({"name": {"type": "string", "description": "Имя или часть имени файла."}}, ["name"]),
        "file_tools", "find_files", "confirm",
    ),
    ToolDefinition(
        "delete_file",
        "Перемещает указанный файл в Корзину macOS.",
        _parameters({"path": {"type": "string", "description": "Полный путь к файлу."}}, ["path"]),
        "file_tools", "delete_file", "confirm",
    ),
    ToolDefinition(
        "analyze_period",
        "Анализирует деятельность пользователя за указанное количество дней.",
        _parameters({"days": {"type": "integer", "description": "Количество последних дней для анализа."}}, ["days"]),
        "analysis", "analyze_period", "auto",
    ),
    ToolDefinition(
        "open_app",
        "Открывает приложение на Mac.",
        _parameters({"app_name": {"type": "string", "description": "Название приложения."}}, ["app_name"]),
        "tools", "open_app", "auto",
    ),
    ToolDefinition(
        "close_app",
        "Закрывает приложение на Mac.",
        _parameters({"app_name": {"type": "string", "description": "Название приложения."}}, ["app_name"]),
        "tools", "close_app", "auto",
    ),
    ToolDefinition(
        "set_volume",
        "Устанавливает громкость Mac от 0 до 100.",
        _parameters({"level": {"type": "integer", "description": "Громкость от 0 до 100."}}, ["level"]),
        "tools", "set_volume", "auto",
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
        "tools", "mute_volume", "auto",
    ),
    ToolDefinition(
        "get_running_apps",
        "Получает список запущенных приложений Mac.",
        _parameters({}),
        "tools", "get_running_apps", "auto",
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
)


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
