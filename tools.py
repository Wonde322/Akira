import subprocess

from memory import add_event


def _run_osascript(script):
    return subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
    )


def set_volume(level: int) -> str:
    """Устанавливает громкость Mac от 0 до 100."""
    if isinstance(level, bool):
        return "Уровень громкости должен быть числом от 0 до 100."

    try:
        level = int(level)
    except (TypeError, ValueError):
        return "Уровень громкости должен быть числом от 0 до 100."

    level = max(0, min(100, level))
    result = _run_osascript("set volume output volume " + str(level))
    if result.returncode != 0:
        return "Не удалось установить громкость."

    message = "Громкость установлена на " + str(level) + "%."
    add_event(message)
    return message


def get_volume() -> str:
    """Возвращает текущую громкость Mac."""
    result = _run_osascript("output volume of (get volume settings)")
    value = result.stdout.strip()
    if result.returncode != 0 or not value:
        return "Не удалось получить текущую громкость."

    return "Текущая громкость: " + value + "%."


def mute_volume() -> str:
    """Выключает звук Mac."""
    result = _run_osascript("set volume with output muted")
    if result.returncode != 0:
        return "Не удалось выключить звук."

    message = "Звук выключен."
    add_event(message)
    return message


def get_running_apps() -> str:
    """Возвращает список запущенных приложений."""
    script = '''
    tell application "System Events"
        set appNames to name of every process whose background only is false
        return appNames
    end tell
    '''

    result = _run_osascript(script)
    if result.returncode != 0:
        return "Не удалось получить список приложений."

    names = result.stdout.strip()
    if not names:
        return "Список запущенных приложений пуст."

    return "Сейчас запущены: " + names
