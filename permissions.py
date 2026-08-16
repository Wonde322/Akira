import json
import os
import threading

from config import PERMISSIONS_FILE
from tool_registry import get_default_tool_permissions


DEFAULT_PERMISSIONS = get_default_tool_permissions()


def save_permissions(permissions, path=PERMISSIONS_FILE):
    with open(path, "w", encoding="utf-8") as file:
        json.dump(
            permissions,
            file,
            ensure_ascii=False,
            indent=2
        )


def prompt_on_stdin(tool_name, arguments):
    """Спрашивает пользователя через stdin (консольный интерфейс)."""
    print()
    print("Акира хочет выполнить действие:")
    print("Инструмент:", tool_name)
    print("Параметры:", arguments)

    answer = input("Разрешить? [да/нет]: ").strip().lower()

    return answer in ["да", "д", "yes", "y"]


def deny_all(tool_name, arguments):
    """Безопасно отклоняет действие, когда контекст не может показать запрос."""
    return False


class PermissionManager:
    """Политика разрешений + провайдер подтверждения для одного контекста.

    Позволяет подключить свой confirmation provider на каждый контекст
    (CLI, Web, Voice) без общего глобального состояния.
    """

    def __init__(self, permission_file, confirmation_provider=prompt_on_stdin):
        self.permission_file = permission_file
        self.confirmation_provider = confirmation_provider
        self._permissions = None
        self._lock = threading.RLock()

    def _load(self):
        if not os.path.exists(self.permission_file):
            save_permissions(DEFAULT_PERMISSIONS.copy(), self.permission_file)
            return DEFAULT_PERMISSIONS.copy()

        try:
            with open(self.permission_file, "r", encoding="utf-8") as file:
                permissions = json.load(file)

            for name, level in DEFAULT_PERMISSIONS.items():
                if name not in permissions:
                    permissions[name] = level

            save_permissions(permissions, self.permission_file)

            return permissions

        except Exception:
            return DEFAULT_PERMISSIONS.copy()

    def _get(self):
        with self._lock:
            if self._permissions is None:
                self._permissions = self._load()

            return self._permissions

    def get_permission(self, tool_name):
        return self._get().get(tool_name, "confirm")

    def set_permission(self, tool_name, level):
        if level not in ["auto", "confirm", "blocked"]:
            return "Недопустимый уровень разрешения."

        with self._lock:
            permissions = self._get()
            permissions[tool_name] = level
            save_permissions(permissions, self.permission_file)

        return (
            "Для " + tool_name +
            " установлен уровень: " + level
        )

    def set_confirmation_provider(self, provider):
        self.confirmation_provider = provider

    def request_confirmation(self, tool_name, arguments):
        provider = self.confirmation_provider

        if provider is None:
            return False

        return bool(provider(tool_name, arguments))


_default_manager = None
_default_manager_lock = threading.Lock()


def _get_default_manager():
    global _default_manager

    if _default_manager is None:
        with _default_manager_lock:
            if _default_manager is None:
                _default_manager = PermissionManager(PERMISSIONS_FILE)

    return _default_manager


def get_permission(tool_name):
    return _get_default_manager().get_permission(tool_name)


def set_permission(tool_name, level):
    return _get_default_manager().set_permission(tool_name, level)


def request_confirmation(tool_name, arguments):
    return _get_default_manager().request_confirmation(tool_name, arguments)


def set_confirmation_provider(provider):
    _get_default_manager().set_confirmation_provider(provider)