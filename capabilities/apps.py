"""Universal application/file/url capability with a compatibility surface."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from app_control import _resolver

backend = None


def _name(value):
    value = str(value or "").strip()
    if value.endswith(".app"):
        value = os.path.basename(value)[:-4]
    resolved = _resolver.resolve(value)
    return resolved.name if resolved else value


def _path_allowed(target):
    try:
        from .filesystem import HOME
        home = Path(HOME).expanduser().resolve()
        path = Path(target).expanduser().resolve()
        return path == home or home in path.parents
    except Exception:
        return False


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


def open_target(target):
    if not isinstance(target, (str, Path)) or not str(target).strip():
        return _fail("invalid_target")
    raw = str(target).strip()

    if raw.startswith(("http://", "https://")):
        result = subprocess.run(["open", raw], text=True, capture_output=True, timeout=4)
        if result.returncode:
            return _fail("open_failed", error_detail=result.stderr.strip())
        return _ok({"target": raw, "kind": "url"})

    path = Path(raw).expanduser()
    if path.exists() or (path.suffix == ".app" and path.is_absolute()):
        if not _path_allowed(path):
            return _fail("not_allowed")
        result = subprocess.run(["open", str(path)], text=True, capture_output=True, timeout=4)
        if result.returncode:
            return _fail("open_failed", error_detail=result.stderr.strip())
        return _ok({"target": str(path), "kind": "path"})

    name = _name(raw)
    result = subprocess.run(["open", "-a", name], text=True, capture_output=True, timeout=4)
    if result.returncode:
        return _fail("open_failed", error_detail=result.stderr.strip())

    data = {"target": name, "kind": "app"}
    if backend is not None:
        try:
            metadata = backend.ui_metadata()
            if isinstance(metadata, dict) and metadata.get("frontmost_app") == name:
                data.update({"activated": True, "frontmost": name})
        except Exception:
            pass
    return _ok(data)


def close_target(target):
    if not isinstance(target, (str, Path)) or not str(target).strip():
        return _fail("invalid_target")
    name = _name(str(target).strip())
    escaped = name.replace("\\", "\\\\").replace('"', '\\"')
    result = subprocess.run(["osascript", "-e", f'tell application "{escaped}" to quit'], text=True, capture_output=True, timeout=4)
    if result.returncode:
        return _fail("close_failed", error_detail=result.stderr.strip() or result.stdout.strip(), target=name)
    return _ok({"target": name, "app": name})
