"""Универсальная отправка клавиатурных комбинаций на Mac.

Принимает только явно описанную комбинацию клавиш (модификаторы +
одна клавиша) из белого списка. Никакие произвольные строки не передаются
в оболочку: валидация выполняется здесь, а исполнение уходит в GUIBackend.
"""

import re

from .backend import KEY_CODES, BackendUnavailable, get_backend
from .protocol import fail, ok

MODIFIER_ALIASES = {
    "command": "command",
    "cmd": "command",
    "⌘": "command",
    "shift": "shift",
    "⇧": "shift",
    "option": "option",
    "opt": "option",
    "alt": "option",
    "⌥": "option",
    "control": "control",
    "ctrl": "control",
    "⌃": "control",
}

backend = None


def _gui_backend():
    if backend is not None:
        return backend

    return get_backend()


def _validate_keys(keys):
    """Разбирает комбинацию и возвращает (base, modifiers) или ValueError."""
    if not isinstance(keys, str) or not keys.strip():
        raise ValueError("Комбинация клавиш не может быть пустой.")

    tokens = [
        token
        for token in re.split(r"[\s+]+", keys.strip().lower())
        if token
    ]

    modifiers = []
    base = None

    for token in tokens:
        if token in MODIFIER_ALIASES:
            modifier = MODIFIER_ALIASES[token]

            if modifier not in modifiers:
                modifiers.append(modifier)

        elif base is None and (len(token) == 1 or token in KEY_CODES):
            base = token

        else:
            raise ValueError("Недопустимая клавиша: " + token)

    if base is None:
        raise ValueError("Не указана основная клавиша.")

    return base, modifiers


def key(keys):
    """Отправляет клавиатурную комбинацию через системный backend."""
    try:
        base, modifiers = _validate_keys(keys)
    except ValueError as error:
        return fail("invalid_keys", str(error))

    try:
        _gui_backend().key_combo(modifiers, base)
    except BackendUnavailable as error:
        return fail("backend_unavailable", str(error))
    except OSError as error:
        return fail("key_failed", str(error))

    return ok({"keys": keys, "action": base})