import json
import os

from tool_registry import get_default_tool_permissions


PERMISSIONS_FILE = "permissions.json"


DEFAULT_PERMISSIONS = {
    **get_default_tool_permissions(),
    "send_message": "confirm",
    "change_system_settings": "confirm",
    "shutdown_computer": "confirm"
}


def load_permissions():
    if not os.path.exists(PERMISSIONS_FILE):
        save_permissions(DEFAULT_PERMISSIONS.copy())
        return DEFAULT_PERMISSIONS.copy()

    try:
        with open(PERMISSIONS_FILE, "r", encoding="utf-8") as file:
            permissions = json.load(file)

        for name, level in DEFAULT_PERMISSIONS.items():
            if name not in permissions:
                permissions[name] = level

        save_permissions(permissions)

        return permissions

    except Exception:
        return DEFAULT_PERMISSIONS.copy()


def save_permissions(permissions):
    with open(PERMISSIONS_FILE, "w", encoding="utf-8") as file:
        json.dump(
            permissions,
            file,
            ensure_ascii=False,
            indent=2
        )


permissions = load_permissions()


def get_permission(tool_name):
    return permissions.get(tool_name, "confirm")


def set_permission(tool_name, level):
    if level not in ["auto", "confirm", "blocked"]:
        return "Недопустимый уровень разрешения."

    permissions[tool_name] = level
    save_permissions(permissions)

    return (
        "Для " + tool_name +
        " установлен уровень: " + level
    )
