"""Universal application/file/url opening and closing capability."""
from __future__ import annotations

from pathlib import Path

from app_control import close_target as _close_target
from app_control import open_target as _open_target


def open_target(target):
    """Open an application, URL or filesystem path without app-specific aliases."""
    if not isinstance(target, (str, Path)) or not str(target).strip():
        return {"success": False, "error": "invalid_target"}
    return _open_target(str(target))


def close_target(target):
    """Close a running application resolved from the macOS application registry."""
    if not isinstance(target, (str, Path)) or not str(target).strip():
        return {"success": False, "error": "invalid_target"}
    return _close_target(str(target))
