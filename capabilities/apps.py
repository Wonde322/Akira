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
    """Extract an application name from either a name or an .app path."""
    if target.endswith(".app") or "/" in target:
        return os.path.basename(target).removesuffix(".app")
    return target


def _confirm_frontmost(app_name):
    try:
        ui = _gui_backend().ui_metadata()
    except Exception:
        return None
    if not isinstance(ui, dict):
        return None
    frontmost = ui.get("frontmost_app")
    if not frontmost:
        return None
    if _app_name_from_target(str(frontmost)).lower() == _app_name_from_target(app_name).lower():
        return frontmost
    return None


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
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
        )
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


def _applescript_escape(text):
    return text.replace("\\", "\\\\").replace('"', '\\"')


def open_target(target):
    """Open an application, URL or file within the filesystem policy."""
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
        command = ["open", "-a", target] if kind == "app" else ["open", target]
        result = subprocess.run(command, capture_output=True, text=True)
    except Exception as error:
        return fail("execution_error", str(error), target=target, kind=kind)
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "").strip() or "Не удалось открыть: " + target
        return fail("open_failed", message, target=target, kind=kind)

    data = {"target": target, "kind": kind}
    if kind == "app":
        running = _wait_for_app_state(target, True)
        if running is False:
            return fail("open_unverified", "Приложение не появилось среди запущенных процессов.", target=target, kind=kind, running=False)
        data["running"] = running
        data["verification"] = "process_state" if running is True else "unavailable"
        frontmost = _confirm_frontmost(target)
        if frontmost:
            data.update(activated=True, frontmost=frontmost)
    return ok(data)


def close_target(target):
    """Close an application by name or .app path and verify process termination."""
    if not isinstance(target, str) or not target.strip():
        return fail("invalid_target", "target должен быть непустой строкой.")
    target = target.strip()
    app_name = _app_name_from_target(target)
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
    return ok({
        "target": target,
        "app": app_name,
        "running": running,
        "verification": "process_state" if running is False else "unavailable",
    })
