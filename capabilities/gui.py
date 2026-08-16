"""Универсальные GUI-примитивы на macOS.

Это тупые исполнительные примитивы:
- не ищут кнопки и элементы;
- не решают, что нажимать;
- не знают про конкретные приложения;
- не обращаются к LLM.

Brain/LLM выбирает действие и координаты, а gui только выполняет его
через инжектируемый GUIBackend (реальный MacOSBackend или FakeBackend
в тестах). select — композиционный примитив «навести указатель и выбрать
элемент в точке», click — сырое нажатие с кнопкой и числом кликов.
"""

from config import (
    MAX_CLICKS,
    MAX_DRAG_DURATION,
    MAX_SCROLL_AMOUNT,
    MAX_TYPE_LENGTH,
)

from .backend import BackendUnavailable, get_backend
from .protocol import fail, ok

BUTTONS = ("left", "right", "middle")
DIRECTIONS = ("up", "down", "left", "right")

backend = None


def _gui_backend():
    if backend is not None:
        return backend

    return get_backend()


def _backend_error(error):
    if isinstance(error, BackendUnavailable):
        return fail("backend_unavailable", str(error))

    return fail("execution_error", str(error))


def _screen_bounds():
    """Возвращает (width, height) основного экрана или (None, None)."""
    try:
        width, height = _gui_backend().screen_size()
        return width, height
    except Exception:
        return None, None


def _check_point(x, y, width, height):
    """Проверяет числовые координаты и границы экрана."""
    if not isinstance(x, (int, float)) or isinstance(x, bool):
        return "invalid_coordinate", "x должен быть числом."

    if not isinstance(y, (int, float)) or isinstance(y, bool):
        return "invalid_coordinate", "y должен быть числом."

    if width is not None:
        if x < 0 or x >= width:
            return "out_of_bounds", "x вне пределов экрана (0.." + str(width - 1) + ")."

        if y < 0 or y >= height:
            return "out_of_bounds", "y вне пределов экрана (0.." + str(height - 1) + ")."

    return None, None


def click(x, y, button="left", clicks=1):
    """Нажимает кнопку мыши в точке (x, y)."""
    width, height = _screen_bounds()
    code, message = _check_point(x, y, width, height)

    if code:
        return fail(code, message)

    if button not in BUTTONS:
        return fail("invalid_button", "button должен быть left/right/middle.")

    if (
        not isinstance(clicks, int)
        or isinstance(clicks, bool)
        or not 1 <= clicks <= MAX_CLICKS
    ):
        return fail(
            "invalid_clicks",
            "clicks должен быть целым числом от 1 до " + str(MAX_CLICKS) + ".",
        )

    x, y = int(x), int(y)

    try:
        _gui_backend().click(x, y, button=button, clicks=clicks)
    except (BackendUnavailable, OSError) as error:
        return _backend_error(error)

    return ok({"x": x, "y": y, "button": button, "clicks": clicks})


def select(x, y):
    """Универсальный выбор: навести указатель и выбрать элемент в точке.

    Композиция из move + одиночный левый клик. Никакого поиска элементов
    по приложениям: работает только с координатами.
    """
    width, height = _screen_bounds()
    code, message = _check_point(x, y, width, height)

    if code:
        return fail(code, message)

    x, y = int(x), int(y)

    try:
        _gui_backend().move_mouse(x, y)
        _gui_backend().click(x, y, button="left", clicks=1)
    except (BackendUnavailable, OSError) as error:
        return _backend_error(error)

    return ok({"x": x, "y": y, "action": "select"})


def _normalize_app_name(name):
    """Нормализует имя приложения для сравнения (без пути и .app)."""
    if not name:
        return ""

    value = str(name).strip()

    if "/" in value:
        value = value.rsplit("/", 1)[-1]

    if value.lower().endswith(".app"):
        value = value[:-4]

    return value


def _frontmost_app():
    """Имя frontmost-приложения через универсальный механизм (ui_metadata)."""
    try:
        ui = _gui_backend().ui_metadata()
    except Exception:
        return None

    if ui:
        return ui.get("frontmost_app")

    return None


# Сколько раз проверяем frontmost после активации: open -a может
# поднять окно с небольшой задержкой.
_ACTIVATE_VERIFY_ATTEMPTS = 4
_ACTIVATE_VERIFY_DELAY = 0.05


def type_text(text, target=None):
    """Печатает текст в целевое приложение (target).

    Порядок: активировать target → проверить, что он frontmost →
    только потом keystroke. Без target текст не печатается
    (target_required). Успех open -a не считается доказательством:
    frontmost проверяется через ui_metadata, и при несовпадении
    текст не отправляется (target_not_frontmost).
    """
    if not isinstance(text, str) or not text:
        return fail("invalid_text", "text должен быть непустой строкой.")

    if len(text) > MAX_TYPE_LENGTH:
        return fail(
            "invalid_text",
            "text слишком длинный (максимум " + str(MAX_TYPE_LENGTH) + " символов).",
        )

    if target is None or not str(target).strip():
        return fail(
            "target_required",
            "target не указан. Укажи приложение, в которое печатать "
            "(обычно frontmost_app из последнего observe).",
        )

    target_name = _normalize_app_name(target)

    try:
        _gui_backend().activate_app(target_name)
    except (BackendUnavailable, OSError) as error:
        return fail(
            "activate_failed",
            "Не удалось активировать " + target_name + ": " + str(error),
            target=target_name,
        )

    import time

    frontmost = None

    for _ in range(_ACTIVATE_VERIFY_ATTEMPTS):
        frontmost = _frontmost_app()

        if _normalize_app_name(frontmost) == target_name:
            break

        time.sleep(_ACTIVATE_VERIFY_DELAY)

    if _normalize_app_name(frontmost) != target_name:
        return fail(
            "target_not_frontmost",
            "Приложение не стало frontmost: ожидалось "
            + target_name + ", frontmost=" + str(frontmost),
            expected=target_name,
            actual=frontmost,
        )

    try:
        _gui_backend().type_text(text)
    except (BackendUnavailable, OSError) as error:
        return _backend_error(error)

    return ok({"typed_chars": len(text), "target": target_name})


def scroll(x=None, y=None, direction="down", amount=1):
    """Прокручивает содержимое под курсором (или в указанной точке)."""
    if direction not in DIRECTIONS:
        return fail("invalid_direction", "direction должен быть up/down/left/right.")

    if (
        not isinstance(amount, int)
        or isinstance(amount, bool)
        or not 1 <= amount <= MAX_SCROLL_AMOUNT
    ):
        return fail(
            "invalid_amount",
            "amount должен быть целым числом от 1 до " + str(MAX_SCROLL_AMOUNT) + ".",
        )

    if x is not None or y is not None:
        width, height = _screen_bounds()
        code, message = _check_point(x, y, width, height)

        if code:
            return fail(code, message)

        x, y = int(x), int(y)

    try:
        _gui_backend().scroll(x, y, direction, amount)
    except (BackendUnavailable, OSError) as error:
        return _backend_error(error)

    return ok(
        {
            "direction": direction,
            "amount": amount,
            "x": x,
            "y": y,
        }
    )


def drag(x1, y1, x2, y2, duration=0.5, button="left"):
    """Перетаскивает объект из точки в точку с заданной длительностью."""
    width, height = _screen_bounds()

    for name, value in (("x1", x1), ("y1", y1), ("x2", x2), ("y2", y2)):
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return fail("invalid_coordinate", name + " должен быть числом.")

    code, message = _check_point(x1, y1, width, height)

    if code:
        return fail(code, message)

    code, message = _check_point(x2, y2, width, height)

    if code:
        return fail(code, message)

    if (
        not isinstance(duration, (int, float))
        or isinstance(duration, bool)
        or not 0 <= duration <= MAX_DRAG_DURATION
    ):
        return fail(
            "invalid_duration",
            "duration должен быть числом от 0 до " + str(MAX_DRAG_DURATION) + ".",
        )

    if button not in BUTTONS:
        return fail("invalid_button", "button должен быть left/right/middle.")

    x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)

    try:
        _gui_backend().drag(x1, y1, x2, y2, duration=duration, button=button)
    except (BackendUnavailable, OSError) as error:
        return _backend_error(error)

    return ok(
        {
            "x1": x1,
            "y1": y1,
            "x2": x2,
            "y2": y2,
            "duration": duration,
            "button": button,
        }
    )