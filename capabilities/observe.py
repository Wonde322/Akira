"""Наблюдение за экраном macOS.

Снимок экрана и размеры экрана получаются через GUIBackend (реальный
MacOSBackend или FakeBackend в тестах). Шаги разделены: получение снимка,
размеры экрана, metadata, UI-данные и интерпретация изображения моделью.

observe описывает происходящее на экране и никогда не решает, куда
кликать: координаты и точки клика в результат не включаются.
"""

import os
from datetime import datetime
from pathlib import Path

from config import SCREENSHOT_DIR, create_groq_client

from .backend import BackendUnavailable, get_backend
from .protocol import fail, ok
from .vision import describe_image

_client = None
backend = None


def _ensure_client():
    global _client

    if _client is None:
        _client = create_groq_client()

    return _client


def _gui_backend():
    if backend is not None:
        return backend

    return get_backend()


def _screenshot_path():
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return SCREENSHOT_DIR / ("screen-" + stamp + ".png")


def capture_screenshot(target=None):
    """Делает снимок экрана и возвращает (path, error)."""
    if target is None:
        target = _screenshot_path()

    try:
        _gui_backend().capture_screenshot(target)
    except (BackendUnavailable, OSError) as error:
        return None, str(error)

    return str(target), None


def screen_size():
    """Возвращает размеры основного экрана macOS."""
    try:
        width, height = _gui_backend().screen_size()
    except (BackendUnavailable, OSError) as error:
        return fail("screen_size_error", str(error))

    return ok({"x": 0, "y": 0, "width": width, "height": height})


def ui_metadata():
    """Возвращает лёгкие UI-данные (frontmost app, окно) или None."""
    try:
        return _gui_backend().ui_metadata()
    except Exception:
        return None


DEFAULT_INTERPRETATION_PROMPT = (
    "Опиши, что происходит на экране, кратко и по существу. "
    "Не предлагай координаты и точки для клика."
)


def observe(interpret=False, description_prompt=None):
    """Снимок экрана + metadata (+ UI-данные, + интерпретация моделью)."""
    path, error = capture_screenshot()

    if error:
        return fail("screenshot_error", error)

    size = screen_size()
    screen = size["data"] if size["success"] else None

    data = {
        "screenshot_path": path,
        "screen": screen,
        "size_bytes": os.path.getsize(path),
    }

    ui = ui_metadata()

    if ui is not None:
        data["ui"] = ui

    if not interpret:
        return ok(data, interpreted=False)

    prompt = description_prompt or DEFAULT_INTERPRETATION_PROMPT

    try:
        description = describe_image(_ensure_client(), path, prompt)
    except Exception as error:
        data["interpretation"] = None
        data["interpretation_error"] = str(error)
        return ok(data, interpreted=False, reason="vision_unsupported")

    data["interpretation"] = description
    return ok(data, interpreted=True)