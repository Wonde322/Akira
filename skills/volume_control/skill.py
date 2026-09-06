"""Natural relative-volume capability built from the existing volume primitive."""

from tool_registry import ToolDefinition


def adjust_volume(direction: str, step: int = 10):
    """Increase or decrease macOS output volume by a relative amount."""
    from tools import get_volume, set_volume

    direction = str(direction or "").strip().casefold()
    try:
        step = int(step)
    except (TypeError, ValueError):
        return "Шаг громкости должен быть числом от 1 до 50."
    step = max(1, min(50, step))

    current_text = get_volume()
    digits = "".join(ch for ch in current_text if ch.isdigit())
    if not digits:
        return current_text
    current = int(digits)

    if direction in {"down", "decrease", "lower", "тише", "уменьшить", "убавить"}:
        target = max(0, current - step)
    elif direction in {"up", "increase", "raise", "громче", "увеличить", "прибавить"}:
        target = min(100, current + step)
    else:
        return "Неизвестное направление изменения громкости."

    return set_volume(target)


TOOLS = (
    ToolDefinition(
        name="adjust_volume",
        description=(
            "Относительно изменяет громкость Mac. Используй для естественных "
            "команд «сделай тише», «потише», «сделай громче», «погромче». "
            "Сначала capability сама узнаёт текущую громкость и затем меняет "
            "её на step процентов; не угадывай абсолютный уровень."
        ),
        parameters={
            "type": "object",
            "properties": {
                "direction": {
                    "type": "string",
                    "enum": ["up", "down"],
                    "description": "up — громче, down — тише.",
                },
                "step": {
                    "type": "integer",
                    "description": "Изменение в процентах, по умолчанию 10.",
                },
            },
            "required": ["direction"],
        },
        implementation_module="skills.volume_control.skill",
        implementation_name="adjust_volume",
        permission_policy="auto",
    ),
)
