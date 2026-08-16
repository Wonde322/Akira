"""Универсальное открытие и закрытие объектов через macOS.

open работает с приложением по имени, с URL или с путём внутри
домашней папки. Пути вне домашней папки отклоняются политикой
файлового слоя.
"""

import os
import subprocess

from .backend import BackendUnavailable, get_backend
from .filesystem import CapabilityError, resolve_path
from .protocol import fail, ok

backend = None


def _gui_backend():
    if backend is not None:
        return backend

    return get_backend()


def _app_name_from_target(target):
    """Извлекает имя приложения из имени или пути к .app."""
    if target.endswith(".app") or "/" in target:
        return os.path.basename(target).removesuffix(".app")

    return target


def _confirm_frontmost(app_name):
    """Пытается подтвердить активацию приложения через ui_metadata.

    Возвращает фактическое имя frontmost приложения, если оно совпадает с
    app_name, иначе None. Никогда не выдумывает подтверждение: при отсутствии
    backend/ui_metadata или несовпадении возвращается None.
    """
    try:
        ui = _gui_backend().ui_metadata()
    except Exception:
        return None

    if not ui:
        return None

    frontmost = ui.get("frontmost_app")

    if not frontmost:
        return None

    if _app_name_from_target(frontmost).lower() == _app_name_from_target(
        app_name
    ).lower():
        return frontmost

    return None


def _classify(target):
    """Определяет тип цели: url, path или app."""
    lowered = target.lower()

    if lowered.startswith(("http://", "https://")):
        return "url"

    if os.path.exists(os.path.expanduser(target)):
        return "path"

    if "/" in target:
        return "path"

    return "app"


def _applescript_escape(text):
    return text.replace("\\", "\\\\").replace('"', '\\"')


def open_target(target):
    """Открывает приложение, URL или файл внутри домашней папки."""
    if not isinstance(target, str) or not target.strip():
        return fail("invalid_target", "target должен быть непустой строкой.")

    target = target.strip()
    kind = _classify(target)

    if kind == "path":
        try:
            target = str(resolve_path(target))
        except CapabilityError as error:
            return fail(error.code, str(error))

    try:
        if kind == "app":
            result = subprocess.run(
                ["open", "-a", target],
                capture_output=True,
                text=True,
            )
        else:
            result = subprocess.run(
                ["open", target],
                capture_output=True,
                text=True,
            )
    except Exception as error:
        return fail("execution_error", str(error), target=target, kind=kind)

    if result.returncode != 0:
        message = (result.stderr or result.stdout or "").strip()

        if not message:
            message = "Не удалось открыть: " + target

        return fail("open_failed", message, target=target, kind=kind)

    data = {"target": target, "kind": kind}

    if kind == "app":
        frontmost = _confirm_frontmost(target)

        if frontmost:
            data["activated"] = True
            data["frontmost"] = frontmost

    return ok(data)


def _app_name_from_target(target):
    """Извлекает имя приложения из имени или пути к .app."""
    if target.endswith(".app") or "/" in target:
        return os.path.basename(target).removesuffix(".app")

    return target


def close_target(target):
    """Закрывает приложение на Mac по имени или пути к .app."""
    if not isinstance(target, str) or not target.strip():
        return fail("invalid_target", "target должен быть непустой строкой.")

    target = target.strip()
    app_name = _app_name_from_target(target)
    script = 'tell application "' + _applescript_escape(app_name) + '" to quit'

    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
        )
    except Exception as error:
        return fail("execution_error", str(error), target=target)

    if result.returncode != 0:
        message = (result.stderr or result.stdout or "").strip()

        if not message:
            message = "Не удалось закрыть: " + target

        return fail("close_failed", message, target=target)

    return ok({"target": target, "app": app_name})
