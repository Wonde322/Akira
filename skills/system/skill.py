"""System diagnostics skill for Akira."""

import os
import platform
import shutil
import subprocess

from tool_registry import ToolDefinition


def system_info():
    """Return compact information about the current machine."""
    return {
        "success": True,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "user": os.environ.get("USER"),
        "home": os.path.expanduser("~"),
        "disk_free_gb": round(shutil.disk_usage(os.path.expanduser("~")).free / 1024**3, 2),
    }


def frontmost_app():
    """Return the currently focused macOS application."""
    try:
        result = subprocess.run(
            [
                "osascript",
                "-e",
                'tell application "System Events" to get name of first application process whose frontmost is true',
            ],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )

        app = result.stdout.strip()

        if not app:
            return {
                "success": False,
                "error": "frontmost_app_unavailable",
            }

        return {
            "success": True,
            "app": app,
        }

    except Exception as exc:
        return {
            "success": False,
            "error": str(exc),
        }


TOOLS = (
    ToolDefinition(
        name="system_info",
        description="Возвращает базовую информацию о Mac: система, архитектура, Python, пользователь, домашняя папка и свободное место.",
        parameters={
            "type": "object",
            "properties": {},
        },
        implementation_module="skills.system.skill",
        implementation_name="system_info",
        permission_policy="auto",
    ),
    ToolDefinition(
        name="frontmost_app",
        description="Возвращает название приложения macOS, которое сейчас находится на переднем плане.",
        parameters={
            "type": "object",
            "properties": {},
        },
        implementation_module="skills.system.skill",
        implementation_name="frontmost_app",
        permission_policy="auto",
    ),
)
