import subprocess

from memory import add_event


def set_volume(level: int) -> str:
    """Устанавливает громкость Mac от 0 до 100."""

    level = max(0, min(100, level))

    subprocess.run([
        "osascript",
        "-e",
        "set volume output volume " + str(level)
    ])

    message = "Громкость установлена на " + str(level) + "%."
    add_event(message)

    return message


def get_volume() -> str:
    """Возвращает текущую громкость Mac."""

    result = subprocess.run(
        [
            "osascript",
            "-e",
            "output volume of (get volume settings)"
        ],
        capture_output=True,
        text=True
    )

    message = "Текущая громкость: " + result.stdout.strip() + "%."
    return message


def mute_volume() -> str:
    """Выключает звук Mac."""

    subprocess.run([
        "osascript",
        "-e",
        "set volume with output muted"
    ])

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

    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        return "Не удалось получить список приложений."

    return "Сейчас запущены: " + result.stdout.strip()
