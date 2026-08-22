"""Системный GUI-бэкенд.

Capability-слой работает через интерфейс GUIBackend, а не размазывает
Quartz/osascript по каждому инструменту. Это позволяет:
- тестировать всю логику через инжектируемый FakeBackend;
- менять системный механизм в одном месте;
- держать GUI-примитивы тупыми исполнительными операциями.

Реальный бэкенд — MacOSBackend:
- движение мыши, клик, скролл, drag — Quartz/CoreGraphics (CGEvent);
- ввод текста и комбинации клавиш — AppleScript System Events (keystroke),
  который корректно обрабатывает Unicode;
- снимок экрана — встроенная утилита screencapture;
- размеры экрана — Quartz, с запасным вариантом через System Events.

Quartz загружается лениво: импорт модуля не требует pyobjc. Без Quartz
доступны только те действия, которым он не нужен (type, key, screenshot,
screen_size, ui_metadata); mouse/click/scroll/drag вернут backend_unavailable.

Ничего из этого слоя не принимает решений: только выполняет действие,
которое выбрал Brain/LLM.
"""

import os
import subprocess
import time

# Коды клавиш macOS (AppleScript System Events "key code").
KEY_CODES = {
    "return": 36,
    "enter": 36,
    "tab": 48,
    "space": 49,
    "delete": 51,
    "escape": 53,
    "esc": 53,
    "forwarddelete": 117,
    "home": 115,
    "end": 119,
    "pageup": 116,
    "pagedown": 121,
    "up": 126,
    "down": 125,
    "left": 123,
    "right": 124,
    "f1": 122,
    "f2": 120,
    "f3": 99,
    "f4": 118,
    "f5": 96,
    "f6": 97,
    "f7": 98,
    "f8": 100,
    "f9": 101,
    "f10": 109,
    "f11": 103,
    "f12": 111,
}

KEY_CODES.update(
    {"f" + str(i): 64 + i for i in range(13, 20)}
)

MODIFIER_TO_APPLESCRIPT = {
    "command": "command down",
    "shift": "shift down",
    "option": "option down",
    "control": "control down",
}


class BackendUnavailable(Exception):
    """Системный механизм недоступен (нет Quartz, нет разрешения и т.п.)."""


class GUIBackend:
    """Интерфейс системных GUI-примитивов.

    Все методы — тупые исполнительные операции без логики приложений.
    """

    def screen_size(self):
        raise NotImplementedError

    def capture_screenshot(self, path):
        raise NotImplementedError

    def move_mouse(self, x, y):
        raise NotImplementedError

    def click(self, x, y, button="left", clicks=1):
        raise NotImplementedError

    def type_text(self, text):
        raise NotImplementedError

    def activate_app(self, app_name):
        raise NotImplementedError

    def key_combo(self, modifiers, key):
        raise NotImplementedError

    def scroll(self, x, y, direction, amount):
        raise NotImplementedError

    def drag(self, x1, y1, x2, y2, duration, button):
        raise NotImplementedError

    def ui_metadata(self):
        """Лёгкие accessibility/UI-данные (best-effort) или None."""
        return None




    def get_frontmost_app(self):
        """Return currently frontmost macOS application."""
        script = (
            'tell application "System Events" '
            'to get name of first application process whose frontmost is true'
        )
        try:
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return result.stdout.strip() or None
        except Exception:
            pass
        return None

    def activate_app(self, app_name):
        """Launch/activate an app and verify focus."""
        if not isinstance(app_name, str) or not app_name.strip():
            return {
                "success": False,
                "error": "app_name is required",
            }

        try:
            result = subprocess.run(
                ["open", "-a", app_name],
                capture_output=True,
                text=True,
                timeout=10,
            )
        except Exception as exc:
            return {
                "success": False,
                "error": str(exc),
            }

        if result.returncode != 0:
            return {
                "success": False,
                "error": result.stderr.strip()
                or f"Could not activate {app_name}",
            }

        deadline = time.time() + 5

        while time.time() < deadline:
            frontmost = self.get_frontmost_app()

            if frontmost and (
                frontmost.casefold() == app_name.casefold()
                or app_name.casefold() in frontmost.casefold()
            ):
                return {
                    "success": True,
                    "app": frontmost,
                    "focused": True,
                }

            time.sleep(0.1)

        return {
            "success": False,
            "app": app_name,
            "focused": False,
            "frontmost": self.get_frontmost_app(),
            "error": "Application did not become frontmost",
        }

    def ensure_app_focus(self, app_name):
        """Recover application focus before keyboard/mouse actions."""
        frontmost = self.get_frontmost_app()

        if frontmost and (
            frontmost.casefold() == app_name.casefold()
            or app_name.casefold() in frontmost.casefold()
        ):
            return {
                "success": True,
                "app": frontmost,
                "focused": True,
                "recovered": False,
            }

        result = self.activate_app(app_name)

        if result.get("success"):
            result["recovered"] = True

        return result
class MacOSBackend(GUIBackend):
    """Реальный бэкенд macOS: Quartz + System Events."""

    def __init__(self):
        self._quartz = None

    def _q(self):
        if self._quartz is None:
            try:
                import Quartz
            except ImportError:
                raise BackendUnavailable(
                    "Действия мыши требуют Quartz (pyobjc-framework-Quartz)."
                )

            self._quartz = Quartz

        return self._quartz

    # ---------- Экран ----------

    def screen_size(self):
        try:
            q = self._q()
            width = q.CGDisplayPixelsWide(q.CGMainDisplayID())
            height = q.CGDisplayPixelsHigh(q.CGMainDisplayID())
            return int(width), int(height)
        except BackendUnavailable:
            return self._screen_size_osascript()

    def _screen_size_osascript(self):
        result = subprocess.run(
            [
                "osascript",
                "-e",
                'tell application "Finder" to get bounds of window of desktop',
            ],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            raise BackendUnavailable("Не удалось получить размеры экрана.")

        parts = [part.strip() for part in result.stdout.split(",")]

        if len(parts) != 4:
            raise BackendUnavailable(
                "Не удалось распознать размеры экрана: " + result.stdout.strip()
            )

        try:
            x1, y1, x2, y2 = (int(part) for part in parts)
        except ValueError:
            raise BackendUnavailable(
                "Не удалось распознать размеры экрана: " + result.stdout.strip()
            )

        return x2 - x1, y2 - y1

    def capture_screenshot(self, path):
        result = subprocess.run(
            ["screencapture", "-x", str(path)],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0 or not os.path.exists(str(path)):
            message = (result.stderr or result.stdout or "").strip()

            if not message:
                message = "Не удалось создать снимок экрана."

            raise OSError(message)

    def ui_metadata(self):
        script = """
        tell application "System Events"
            set frontApp to first application process whose frontmost is true
            set appName to name of frontApp
            try
                set winTitle to name of front window of frontApp
            on error
                set winTitle to ""
            end try
            return appName & "|" & winTitle
        end tell
        """

        try:
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
            )
        except Exception:
            return None

        if result.returncode != 0:
            return None

        app_name, _, window_title = result.stdout.strip().partition("|")

        return {
            "frontmost_app": app_name.strip(),
            "window_title": window_title.strip(),
        }

    # ---------- Мышь (Quartz) ----------

    def _mouse_button(self, button):
        q = self._q()

        if button == "right":
            return (
                q.kCGEventRightMouseDown,
                q.kCGEventRightMouseUp,
                q.kCGEventRightMouseDragged,
                q.kCGMouseButtonRight,
            )

        if button == "middle":
            return (
                q.kCGEventOtherMouseDown,
                q.kCGEventOtherMouseUp,
                q.kCGEventOtherMouseDragged,
                q.kCGMouseButtonCenter,
            )

        return (
            q.kCGEventLeftMouseDown,
            q.kCGEventLeftMouseUp,
            q.kCGEventLeftMouseDragged,
            q.kCGMouseButtonLeft,
        )

    def _post_mouse(self, event_type, x, y, button):
        q = self._q()
        event = q.CGEventCreateMouseEvent(None, event_type, (x, y), button)
        q.CGEventPost(q.kCGHIDEventTap, event)

    def move_mouse(self, x, y):
        q = self._q()
        point = (x, y)
        q.CGWarpMouseCursorPosition(point)
        self._post_mouse(q.kCGEventMouseMoved, x, y, 0)

    def click(self, x, y, button="left", clicks=1):
        self.move_mouse(x, y)
        down, up, _, mouse_button = self._mouse_button(button)

        for _ in range(clicks):
            self._post_mouse(down, x, y, mouse_button)
            self._post_mouse(up, x, y, mouse_button)

    def scroll(self, x, y, direction, amount):
        q = self._q()

        if x is not None and y is not None:
            self.move_mouse(x, y)

        delta = amount if direction == "down" else -amount

        if direction in ("left", "right"):
            delta = amount if direction == "right" else -amount
            event = q.CGEventCreateScrollWheelEvent(
                None,
                q.kCGScrollEventUnitPixel,
                2,
                0,
                delta,
            )
        else:
            event = q.CGEventCreateScrollWheelEvent(
                None,
                q.kCGScrollEventUnitPixel,
                1,
                delta,
            )

        q.CGEventPost(q.kCGHIDEventTap, event)

    def drag(self, x1, y1, x2, y2, duration, button):
        self.move_mouse(x1, y1)
        down, up, dragged, mouse_button = self._mouse_button(button)
        self._post_mouse(down, x1, y1, mouse_button)

        steps = max(2, int(duration * 60))

        try:
            for index in range(1, steps + 1):
                ratio = index / steps
                cx = int(x1 + (x2 - x1) * ratio)
                cy = int(y1 + (y2 - y1) * ratio)
                self._post_mouse(dragged, cx, cy, mouse_button)

                if duration > 0:
                    time.sleep(duration / steps)
        finally:
            self._post_mouse(up, x2, y2, mouse_button)

    # ---------- Клавиатура (System Events) ----------

    def _run_osascript(self, script):
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            message = (result.stderr or result.stdout or "").strip()

            if not message:
                message = "osascript не выполнился."

            raise OSError(message)

    def _applescript_string(self, value):
        """Экранирует текст как литерал AppleScript (без shell)."""
        parts = []

        for line in value.split("\n"):
            escaped = line.replace("\\", "\\\\").replace('"', '\\"')
            parts.append('"' + escaped + '"')

        return " & linefeed & ".join(parts)

    def type_text(self, text):
        script = (
            'tell application "System Events" to keystroke '
            + self._applescript_string(text)
        )
        self._run_osascript(script)

    def activate_app(self, app_name):
        """Активирует (поднимает на передний план) приложение по имени.

        Использует системный `open -a`: универсальный механизм macOS,
        работающий и с запущенным приложением, и с .app на диске.
        Успех open -a не доказывает, что приложение стало frontmost:
        это проверяет gui.type_text через ui_metadata().
        """
        result = subprocess.run(
            ["open", "-a", app_name],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            message = (result.stderr or result.stdout or "").strip()

            if not message:
                message = "Не удалось активировать приложение: " + app_name

            raise OSError(message)

    def key_combo(self, modifiers, key):
        modifier_clause = ""

        if modifiers:
            names = [MODIFIER_TO_APPLESCRIPT[name] for name in modifiers]
            modifier_clause = " using {" + ", ".join(names) + "}"

        if len(key) == 1:
            escaped = key.replace("\\", "\\\\").replace('"', '\\"')
            action = 'keystroke "' + escaped + '"'
        else:
            action = "key code " + str(KEY_CODES[key])

        script = 'tell application "System Events" to ' + action + modifier_clause
        self._run_osascript(script)


_default_backend = None


def get_backend():
    """Возвращает единственный реальный бэкенд macOS."""
    global _default_backend

    if _default_backend is None:
        _default_backend = MacOSBackend()

    return _default_backend