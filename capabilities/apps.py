"""Fast direct macOS application control."""
from __future__ import annotations
import os
import subprocess


def _ok(**data): return {"success": True, **data}
def _fail(error, **data): return {"success": False, "error": str(error), **data}

def _name(value):
    value = str(value or "").strip()
    return os.path.basename(value)[:-4] if value.endswith(".app") else value

def _quote(value): return str(value).replace("\\", "\\\\").replace('"', '\\"')

def _run(script, timeout=3):
    try: return subprocess.run(["osascript", "-e", script], text=True, capture_output=True, timeout=timeout)
    except Exception as exc: return None, str(exc)

def open_target(target):
    name = _name(target)
    if not name: return _fail("invalid target")
    try:
        launched = subprocess.run(["open", "-a", name], text=True, capture_output=True, timeout=4)
    except Exception as exc: return _fail(exc, target=name)
    if launched.returncode != 0:
        return _fail(launched.stderr.strip() or "open failed", target=name)
    # `open -a` is the launch operation. Activation is intentionally quick and
    # never waits for Accessibility/System Events or window polling.
    result = _run('tell application "' + _quote(name) + '" to activate')
    if isinstance(result, tuple): return _ok(target=name, state="opened")
    return _ok(target=name, state="opened") if result.returncode == 0 else _ok(target=name, state="opened")

def close_target(target):
    name = _name(target)
    if not name: return _fail("invalid target")
    result = _run('tell application "' + _quote(name) + '" to quit')
    if isinstance(result, tuple): return _fail(result[1], target=name)
    if result.returncode != 0:
        return _fail(result.stderr.strip() or result.stdout.strip() or "quit failed", target=name)
    return _ok(target=name, state="closed")
