"""Дружелюбные подписи действий Акиры для desktop UI.

Никакой сырой JSON/истории рассуждений: только короткие человеческие фразы.
"""

ACTIVITY_LABELS = {
    "open": "Открываю приложение",
    "close": "Закрываю приложение",
    "type": "Ввожу текст",
    "key": "Нажимаю клавиши",
    "click": "Выполняю действие",
    "select": "Выбираю элемент",
    "scroll": "Прокручиваю",
    "drag": "Перетаскиваю",
    "observe": "Наблюдаю экран",
    "screen_size": "Проверяю экран",
    "open_youtube": "Открываю YouTube",
    "play_spotify": "Включаю музыку",
    "analyze_period": "Анализирую активность",
    "analyze_goals": "Проверяю цели",
    "check_proactive": "Проверяю важное",
    "find": "Ищу файлы",
    "read": "Читаю файл",
    "write": "Записываю файл",
    "create": "Создаю файл",
    "move": "Перемещаю файл",
    "copy": "Копирую файл",
    "rename": "Переименовываю файл",
    "delete": "Удаляю файл",
    "shell": "Выполняю команду",
    "wait": "Ожидаю",
    "get_running_apps": "Проверяю приложения",
    "get_volume": "Проверяю громкость",
    "set_volume": "Меняю громкость",
    "mute_volume": "Выключаю звук",
    "add_goal": "Запоминаю цель",
    "get_goals": "Смотрю цели",
    "add_task": "Запоминаю задачу",
    "get_tasks": "Смотрю задачи",
    "complete_task": "Отмечаю задачу",
    "add_event": "Запоминаю событие",
    "get_recent_events": "Смотрю события",
    "finish_task": "Проверяю результат",
}

FALLBACK_LABEL = "Выполняю действие"


def activity_label(tool_name):
    """Возвращает короткую подпись действия для tool_name."""
    return ACTIVITY_LABELS.get(tool_name, FALLBACK_LABEL)


def describe_action(tool_name, arguments=None):
    """Человекочитаемое описание действия для подтверждения.

    Никакого сырого JSON: только имя действия и, если уместно,
    имя приложения/файла.
    """
    arguments = arguments or {}

    if tool_name == "open" and arguments.get("target"):
        return f"Открыть: {arguments['target']}"

    if tool_name == "close" and arguments.get("target"):
        return f"Закрыть: {arguments['target']}"

    if tool_name == "type":
        target = arguments.get("target")
        if target:
            return f"Ввести текст в: {target}"
        return "Ввести текст"

    if tool_name == "key" and arguments.get("keys"):
        return f"Нажать клавиши: {arguments['keys']}"

    if tool_name == "shell" and arguments.get("command"):
        return "Выполнить команду в терминале"

    if tool_name == "write" and arguments.get("path"):
        return f"Записать файл: {arguments['path']}"

    if tool_name == "create" and arguments.get("path"):
        return f"Создать: {arguments['path']}"

    if tool_name == "delete" and arguments.get("path"):
        return f"Удалить: {arguments['path']}"

    if tool_name in ("move", "copy", "rename") and arguments.get("source"):
        return f"Работа с файлом: {arguments['source']}"

    return ACTIVITY_LABELS.get(tool_name, FALLBACK_LABEL)