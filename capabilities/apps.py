"""Universal opening and closing of applications, URLs and allowed paths on macOS."""

import os
import subprocess
import time

from .backend import get_backend
from .filesystem import CapabilityError, resolve_path
from .protocol import fail, ok

backend = None


def _gui_backend():
    return backend if backend is not None else get_backend()


def _app_name_from_target(target):
    if target.endswith(".app") or "/" in target:
        return os.path.basename(target).removesuffix(".app")
    return target


def _applescript_escape(text):
    return text.replace("\\", "\\\\").replace('"', '\\"')


def _frontmost_app():
    try:
        ui = _gui_backend().ui_metadata()
    except Exception:
        return None
    return ui.get("frontmost_app") if isinstance(ui, dict) else None


def _wait_for_frontmost(app_name, timeout=3.0):
    expected = _app_name_from_target(app_name).casefold()
    deadline = time.monotonic() + timeout
    current = _frontmost_app()
    while time.monotonic() < deadline:
        if current and _app_name_from_target(str(current)).casefold() == expected:
            return current
        time.sleep(0.1)
        current = _frontmost_app()
    return current if current and _app_name_from_target(str(current)).casefold() == expected else None


def _activate_app(app_name):
    """Bring an existing application, including a minimized one, to the front."""
    escaped = _applescript_escape(app_name)
    script = f'tell application "{escaped}" to activate'
    try:
        result = subprocess.run(
            ["osascript", "-e", script], capture_output=True, text=True
        )
    except Exception as error:
        return False, str(error)
    if result.returncode != 0:
        return False, (result.stderr or result.stdout or "activation failed").strip()
    return True, None


def app_running(target):
    """Return actual process state; Dock icons and screenshots are not evidence."""
    app_name = _app_name_from_target(str(target).strip())
    if not app_name:
        return False
    script = (
        'tell application "System Events" to '
        'return exists (process "' + _applescript_escape(app_name) + '")'
    )
    try:
        result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    except Exception:
        return None
    if result.returncode != 0:
        return None
    value = result.stdout.strip().lower()
    if value == "true":
        return True
    if value == "false":
        return False
    return None


def _wait_for_app_state(target, expected, timeout=5.0):
    deadline = time.monotonic() + timeout
    last = app_running(target)
    while time.monotonic() < deadline:
        if last is expected:
            return last
        time.sleep(0.1)
        last = app_running(target)
    return last


def _classify(target):
    lowered = target.lower()
    if lowered.startswith(("http://", "https://")):
        return "url"
    if os.path.exists(os.path.expanduser(target)) or "/" in target:
        return "path"
    return "app"


def open_target(target):
    """Open or activate an application, URL or allowed file path."""
    if not isinstance(target, str) or not target.strip():
        return fail("invalid_target", "target должен быть непустой строкой.")
    target = target.strip()
    kind = _classify(target)
    if kind == "path":
        try:
            target = str(resolve_path(target))
        except CapabilityError as error:
            return fail(error.code, str(error))

    app_name = _app_name_from_target(target) if kind == "app" else None
    was_running = app_running(app_name) if app_name else None
    try:
        if kind == "app" and was_running is True:
            # Do not launch a second route or ask the agent to use Terminal.
            # Explicit activation is the correct operation for a minimized app.
            activated, error = _activate_app(app_name)
            if not activated:
                return fail("activate_failed", error or "Не удалось активировать приложение.", target=target, kind=kind)
        else:
            command = ["open", "-a", target] if kind == "app" else ["open", target]
            result = subprocess.run(command, capture_output=True, text=True)
            if result.returncode != 0:
                message = (result.stderr or result.stdout or "").strip() or "Не удалось открыть: " + target
                return fail("open_failed", message, target=target, kind=kind)
            if kind == "app":
                _activate_app(app_name)
    except Exception as error:
        return fail("execution_error", str(error), target=target, kind=kind)

    data = {"target": target, "kind": kind}
    if kind == "app":
        running = _wait_for_app_state(app_name, True)
        if running is False:
            return fail("open_unverified", "Приложение не появилось среди запущенных процессов.", target=target, kind=kind, running=False)
        data["running"] = running
        data["verification"] = "process_state" if running is True else "unavailable"
        frontmost = _wait_for_frontmost(app_name)
        if frontmost:
            data.update(activated=True, frontmost=frontmost)
        else:
            data["activated"] = False
    return ok(data)


def close_target(target):
    """Close an application by name or .app path and verify process termination."""
    if not isinstance(target, str) or not target.strip():
        return fail("invalid_target", "target должен быть непустой строкой.")
    target = target.strip()
    app_name = _app_name_from_target(target)
    if app_running(app_name) is False:
        return ok({"target": target, "app": app_name, "running": False, "verification": "process_state"})
    script = 'tell application "' + _applescript_escape(app_name) + '" to quit'
    try:
        result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    except Exception as error:
        return fail("execution_error", str(error), target=target)
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "").strip() or "Не удалось закрыть: " + target
        return fail("close_failed", message, target=target)

    running = _wait_for_app_state(app_name, False)
    if running is True:
        return fail("close_unverified", "Приложение всё ещё присутствует среди запущенных процессов.", target=target, app=app_name, running=True)
    return ok({"target": target, "app": app_name, "running": running, "verification": "process_state" if running is False else "unavailable"})