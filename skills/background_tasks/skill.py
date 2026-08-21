"""Background agent task tools."""

from tool_registry import ToolDefinition, _parameters

TOOLS = (
    ToolDefinition(
        "background_task_start",
        "Запускает независимую долгую задачу Акиры в отдельном execution context и сразу возвращает task_id.",
        _parameters({
            "goal": {
                "type": "string",
                "description": "Конкретная цель фоновой задачи.",
            },
        }, ["goal"]),
        "background_tasks",
        "background_task_start",
        "auto",
    ),
    ToolDefinition(
        "background_task_status",
        "Возвращает текущий статус фоновой задачи по task_id.",
        _parameters({
            "task_id": {
                "type": "string",
                "description": "Идентификатор фоновой задачи.",
            },
        }, ["task_id"]),
        "background_tasks",
        "background_task_status",
        "auto",
    ),
    ToolDefinition(
        "background_task_result",
        "Возвращает итог или ошибку завершённой фоновой задачи. Для выполняющейся задачи сообщает текущий статус.",
        _parameters({
            "task_id": {
                "type": "string",
                "description": "Идентификатор фоновой задачи.",
            },
        }, ["task_id"]),
        "background_tasks",
        "background_task_result",
        "auto",
    ),
)
