"""Native macOS application control built on Launch Services/System Events."""
from __future__ import annotations

import subprocess
import time
from pathlib import Path

from computer_state import ApplicationResolver

_resolver = ApplicationResolver()


def _ok(**data):
    return {"success": True, "data": data}


def _fail(error, **data):
    return {"success": False, "error": error, "data": data}


def open_application(target: str):
    app = _resolver.resolve(target)
    if app is None:
        return _fail("application_not_found", target=target)
    try:
        result = subprocess.run(["open", app.path], text=True, capture_output=True, timeout=3)
    except Exception as exc:
        return _fail("open_failed", target=app.name, detail=str(exc))
    if result.returncode:
        return _fail("open_failed", target=app.name, detail=result.stderr.strip())
    return _ok(action="open", application=app.name, path=app.path, bundle_id=app.bundle_id)


def close_application(target: str):
    app = _resolver.resolve(target, running_only=True)
    if app is None:
        return _fail("application_not_running", target=target)

    escaped = app.name.replace("\\", "\\\\").replace('"', '\\"')
    script = f'''set appName to "{escaped}"
tell application appName to quit'''
    try:
        result = subprocess.run(["osascript", "-e", script], text=True, capture_output=True, timeout=3)
    except Exception as exc:
        return _fail("close_failed", target=app.name, detail=str(exc))
    if result.returncode:
        return _fail("close_failed", target=app.name, detail=result.stderr.strip())

    deadline = time.monotonic() + 1.5
    while time.monotonic() < deadline:
        if _resolver.resolve(app.name, running_only=True) is None:
            return _ok(action="close", application=app.name, closed=True)
        time.sleep(0.05)
    return _ok(action="close", application=app.name, closed=False, pending=True)


def open_target(target: str):
    raw = str(target or "").strip()
    if raw.startswith(("http://", "https://")):
        try:
            result = subprocess.run(["open", raw], text=True, capture_output=True, timeout=3)
            if result.returncode:
                return _fail("open_failed", target=raw, detail=result.stderr.strip())
            return _ok(action="open", target=raw, kind="url")
        except Exception as exc:
            return _fail("open_failed", target=raw, detail=str(exc))

    path = Path(raw).expanduser()
    if path.exists():
        try:
            result = subprocess.run(["open", str(path)], text=True, capture_output=True, timeout=3)
            if result.returncode:
                return _fail("open_failed", target=str(path), detail=result.stderr.strip())
            return _ok(action="open", target=str(path), kind="path")
        except Exception as exc:
            return _fail("open_failed", target=str(path), detail=str(exc))

    return open_application(raw)


def close_target(target: str):
    return close_application(str(target or "").strip())
