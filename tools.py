import subprocess
import os

from memory import add_event


def open_app(app_name: str) -> str:
    """Открывает приложение на Mac."""

    applications = "/Applications"

    for app in os.listdir(applications):
        if app.lower().endswith(".app"):
            name = app[:-4]

            if app_name.lower() in name.lower():
                subprocess.Popen(["open", "-a", name])

                result = name + " запущен."
                add_event(result)

                return result

    result = "Приложение " + app_name + " не найдено."
    add_event(result)

    return result


def close_app(app_name: str) -> str:
    """Закрывает приложение на Mac."""

    result = subprocess.run(
        [
            "osascript",
            "-e",
            'tell application "' + app_name + '" to quit'
        ],
        capture_output=True,
        text=True
    )

    if result.returncode == 0:
        message = app_name + " закрыт."
        add_event(message)
        return message

    message = "Не удалось закрыть " + app_name + "."
    add_event(message)

    return message


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
