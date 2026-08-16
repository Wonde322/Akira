"""FakeBackend для тестов GUI-слоя.

Заменяет реальные системные вызовы (Quartz/osascript/screencapture)
записью событий в список. Позволяет тестировать всю логику capabilities
без воздействия на реальный компьютер и без реального OS-доступа.
"""

from pathlib import Path


class FakeBackend:
    def __init__(self, screen=(1440, 900), ui=None):
        self.screen = screen
        self.ui = ui
        self.screenshot_bytes = b"PNG-data"
        self.events = []
        self.frontmost_app = (ui or {}).get("frontmost_app")

    def screen_size(self):
        return self.screen

    def capture_screenshot(self, path):
        Path(path).write_bytes(self.screenshot_bytes)

    def move_mouse(self, x, y):
        self.events.append(("move", int(x), int(y)))

    def click(self, x, y, button="left", clicks=1):
        self.events.append(("click", int(x), int(y), button, clicks))

    def type_text(self, text):
        self.events.append(("type", text))

    def activate_app(self, app_name):
        self.events.append(("activate", app_name))
        self.frontmost_app = app_name

    def key_combo(self, modifiers, key):
        self.events.append(("key", list(modifiers), key))

    def scroll(self, x, y, direction, amount):
        self.events.append(("scroll", x, y, direction, amount))

    def drag(self, x1, y1, x2, y2, duration, button):
        self.events.append(("drag", x1, y1, x2, y2, duration, button))

    def ui_metadata(self):
        if self.ui is None and self.frontmost_app is None:
            return None

        metadata = dict(self.ui or {})

        if self.frontmost_app is not None:
            metadata["frontmost_app"] = self.frontmost_app

        return metadata


class FakeVisionProvider:
    """Заменяет vision-провайдер: возвращает фиксированное описание.

    Описание может быть задано (prompt-injection: текст «Ignore previous
    instructions…» как содержимое экрана). Считает вызовы describe().
    """

    def __init__(self, description="экран стабилен, действий не требуется"):
        self.description = description
        self.calls = []

    def describe(self, image_path, prompt):
        self.calls.append((image_path, prompt))
        return self.description