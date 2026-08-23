"""Direct macOS application control.

No agent loop, screenshots, Dock inspection or terminal fallback.
"""
from __future__ import annotations

import os
import subprocess
import time


def _ok(**data):
    return {"success": True, **data}


def _fail(error, **data):
    return {"success": False, "error": str(error), **data}


def _name(value):
    value = str(value or "").strip()
    if value.endswith(".app"):
        value = os.path.basename(value)[:-4]
    return value


def _quote(value):
    return str(value).replace('\\', '\\\\').replace('"', '\\"')


def _run(script, timeout=8):
    try:
        return subprocess.run(["osascript", "-e", script], text=True, capture_output=True, timeout=timeout)
    except Exception as exc:
        return None, str(exc)


def is_running(target):
    name = _name(target)
    if not name:
        return False
    result = _run('tell application "System Events" to return exists process "' + _quote(name) + '"')
    if isinstance(result, tuple):
        return False
    return result.returncode == 0 and result.stdout.strip().casefold() == "true"


def _activate(name):
    # Activation itself must not depend on Accessibility permission.
    result = _run('tell application "' + _quote(name) + '" to activate')
    if isinstance(result, tuple):
        return False, result[1]
    if result.returncode != 0:
        return False, (result.stderr or result.stdout or "activation failed").strip()

    # Restoring minimized windows is best-effort only.
    _run(
        'tell application "System Events" to tell process "' + _quote(name) + '"\n'
        'try\n'
        'repeat with w in windows\n'
        'try\n'
        'if value of attribute "AXMinimized" of w then set value of attribute "AXMinimized" of w to false\n'
        'end try\n'
        'end repeat\n'
        'set frontmost to true\n'
        'end try\n'
        'end tell'
    )
    return True, None


def _wait(name, expected, timeout=6):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if is_running(name) == expected:
            return True
        time.sleep(0.1)
    return is_running(name) == expected


def open_target(target):
    name = _name(target)
    if not name:
        return _fail("invalid target")
    if is_running(name):
        success, error = _activate(name)
        return _ok(target=name, state="active") if success else _fail(error, target=name)
    try:
        launched = subprocess.run(["open", "-a", name], text=True, capture_output=True, timeout=12)
    except Exception as exc:
        return _fail(exc, target=name)
    if launched.returncode != 0:
        return _fail(launched.stderr.strip() or "open failed", target=name)
    if not _wait(name, True):
        # Some apps use a different process name. `open -a` succeeding is still
        # a valid launch; activate by application name instead of failing here.
        success, error = _activate(name)
        return _ok(target=name, state="active") if success else _fail(error or "launch failed", target=name)
    success, error = _activate(name)
    return _ok(target=name, state="active") if success else _fail(error, target=name)


def close_target(target):
    name = _name(target)
    if not name:
        return _fail("invalid target")
    result = _run('tell application "' + _quote(name) + '" to quit')
    if isinstance(result, tuple):
        return _fail(result[1], target=name)
    if result.returncode != 0:
        return _fail(result.stderr.strip() or result.stdout.strip() or "quit failed", target=name)
    return _ok(target=name, state="closed")
