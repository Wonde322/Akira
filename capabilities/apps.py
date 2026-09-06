"""Generic application/file/url opening and application closing capability."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path


# Compatibility injection point used by the macOS capability tests and by the
# real backend when available.  It is deliberately optional on non-macOS hosts.
backend = None


def _ok(data=None, **extra):
    result = {"success": True}
    if data is not None:
        result["data"] = data
    result.update(extra)
    return result


def _fail(error, data=None, **extra):
    result = {"success": False, "error": str(error)}
    if data is not None:
        result["data"] = data
    result.update(extra)
    return result


def _name(value):
    value = str(value or "").strip()
    return os.path.basename(value)[:-4] if value.endswith(".app") else value


def _quote(value):
    return str(value).replace("\\", "\\\\").replace('"', '\\"')


def _run(script, timeout=3):
    try:
        return subprocess.run(
            ["osascript", "-e", script],
            text=True,
            capture_output=True,
            timeout=timeout,
        )
    except Exception as exc:
        return None, str(exc)


def _path_allowed(target):
    try:
        from .filesystem import HOME
        home = Path(HOME).expanduser().resolve()
        path = Path(target).expanduser().resolve()
        return path == home or home in path.parents
    except Exception:
        return False


def _backend_metadata():
    if backend is None:
        return None
    try:
        return backend.ui_metadata()
    except Exception:
        return None


def open_target(target):
    raw = str(target or "").strip()
    if not raw or not isinstance(target, (str, Path)):
        return _fail("invalid_target")

    # URL: open directly, never force an application-specific route.
    if raw.startswith(("http://", "https://")):
        try:
            result = subprocess.run(["open", raw], text=True, capture_output=True, timeout=4)
        except Exception as exc:
            return _fail("open_failed", error_detail=str(exc))
        if result.returncode != 0:
            return _fail("open_failed", error_detail=result.stderr.strip())
        return _ok({"target": raw, "kind": "url"})

    path = Path(raw).expanduser()
    if path.exists() or (path.suffix == ".app" and path.is_absolute()):
        if not _path_allowed(path):
            return _fail("not_allowed")
        try:
            result = subprocess.run(["open", str(path)], text=True, capture_output=True, timeout=4)
        except Exception as exc:
            return _fail("open_failed", error_detail=str(exc))
        if result.returncode != 0:
            return _fail("open_failed", error_detail=result.stderr.strip())
        return _ok({"target": str(path), "kind": "path"})

    name = _name(raw)
    if not name:
        return _fail("invalid_target")
    try:
        launched = subprocess.run(["open", "-a", name], text=True, capture_output=True, timeout=4)
    except Exception as exc:
        return _fail("open_failed", error_detail=str(exc))
    if launched.returncode != 0:
        return _fail("open_failed", error_detail=launched.stderr.strip())

    data = {"target": name, "kind": "app"}
    metadata = _backend_metadata()
    if isinstance(metadata, dict) and metadata.get("frontmost_app") == name:
        data.update({"activated": True, "frontmost": name})
    return _ok(data)


def close_target(target):
    raw = str(target or "").strip()
    name = _name(raw)
    if not name:
        return _fail("invalid_target")
    result = _run(f'tell application "{_quote(name)}" to quit')
    if isinstance(result, tuple):
        return _fail("close_failed", error_detail=result[1], target=name)
    if result.returncode != 0:
        return _fail("close_failed", error_detail=result.stderr.strip() or result.stdout.strip(), target=name)
    return _ok({"target": name, "app": name})
