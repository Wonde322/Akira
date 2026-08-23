"""Minimal macOS application controller.

This module has one job: open/activate and close applications using macOS APIs.
It never uses the Dock, screenshots, agent observation or Terminal fallbacks.
"""
from __future__ import annotations

import os
import subprocess
import time


def _result(success: bool, **data):
    return {"success": success, **data}


def _name(value: str) -> str:
    value = str(value or "").strip()
    if value.endswith(".app"):
        value = os.path.basename(value)[:-4]
    return value


def _osascript(source: str):
    try:
        return subprocess.run(
            ["osascript", "-e", source],
            text=True,
            capture_output=True,
            timeout=8,
        )
    except Exception as exc:
        return None, str(exc)


def is_running(target: str):
    name = _name(target)
    if not name:
        return False
    # pgrep is used only as authoritative process state, never as execution.
    result = subprocess.run(
        ["pgrep", "-x", name], text=True, capture_output=True
    )
    return result.returncode == 0


def _activate(name: str):
    quoted = name.replace('"', '\\"')
    script = (
        f'tell application "{quoted}" to activate\n'
        f'tell application "System Events" to tell process "{quoted}"\n'
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
    result = _osascript(script)
    if isinstance(result, tuple):
        return False, result[1]
    if result.returncode != 0:
        return False, (result.stderr or result.stdout or "activation failed").strip()
    return True, None


def _wait_for(target: str, running: bool, timeout: float = 5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if is_running(target) == running:
            return True
        time.sleep(0.1)
    return is_running(target) == running


def open_target(target: str):
    name = _name(target)
    if not name:
        return _result(False, error="invalid_target")

    # Existing, including minimized, applications are activated first.
    if is_running(name):
        activated, error = _activate(name)
        if activated:
            return _result(True, target=name, state="active")
        return _result(False, target=name, error=error or "activate_failed")

    try:
        launched = subprocess.run(
            ["open", "-a", name], text=True, capture_output=True, timeout=12
        )
    except Exception as exc:
        return _result(False, target=name, error=str(exc))
    if launched.returncode != 0:
        return _result(False, target=name, error=(launched.stderr or "open_failed").strip())
    if not _wait_for(name, True):
        return _result(False, target=name, error="launch_unverified")
    activated, error = _activate(name)
    if not activated:
        return _result(False, target=name, error=error or "activate_failed")
    return _result(True, target=name, state="active")


def close_target(target: str):
    name = _name(target)
    if not name:
        return _result(False, error="invalid_target")
    if not is_running(name):
        return _result(True, target=name, state="closed")
    quoted = name.replace('"', '\\"')
    result = _osascript(f'tell application "{quoted}" to quit')
    if isinstance(result, tuple):
        return _result(False, target=name, error=result[1])
    if result.returncode != 0:
        return _result(False, target=name, error=(result.stderr or "quit_failed").strip())
    if not _wait_for(name, False):
        return _result(False, target=name, error="close_unverified")
    return _result(True, target=name, state="closed")
