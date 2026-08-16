"""Главное окно desktop-приложения Akira.

Единая state machine приложения: IDLE / LISTENING / THINKING / SPEAKING /
CONFIRMING / DISABLED. Сфера — главный индикатор состояния. Кнопка
микрофона — независимый toggle голосового ввода, управляемый сигналом
микрофона движка. Клик по сфере — отдельный toggle dialogue mode.

Принцип: UI — отражение состояния движка. Никаких «симулированных» кнопок:
если состояние изменилось, UI меняется; если вернулось — возвращается.
"""

import os
import sys

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .confirmation import ConfirmationService
from .visualizer import HalftoneWidget
from .voice import VoiceEngine
from .worker import BrainWorker

BACKGROUND = QColor(16, 16, 19, 250)
BORDER = QColor(44, 44, 54, 190)
TEXT = QColor(232, 232, 238)
MUTED = QColor(140, 140, 152)
ACCENT = QColor(255, 60, 75)

BUBBLE_AKIRA_BG = QColor(30, 30, 36, 210)
BUBBLE_AKIRA_BORDER = QColor(255, 255, 255, 14)
BUBBLE_AKIRA_TEXT = QColor(228, 228, 236)
BUBBLE_USER_BG = QColor(126, 22, 38, 230)
BUBBLE_USER_BORDER = QColor(255, 80, 98, 60)
BUBBLE_USER_TEXT = QColor(252, 246, 247)

INPUT_BG = QColor(22, 22, 27, 255)
INPUT_BORDER = QColor(48, 48, 58, 255)


class TrafficLight(QWidget):
    """Одна круглая кнопка в стиле macOS traffic light."""

    def __init__(self, color, action, parent=None):
        super().__init__(parent)
        self._color = QColor(color)
        self._action = action
        self.setFixedSize(14, 14)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._action()
            event.accept()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._color)
        painter.drawEllipse(0, 0, self.width() - 1, self.height() - 1)


class Bubble(QLabel):
    """Bubble-сообщение: скруглённый полупрозрачный блок с переносом текста.

    Ширина пузыря задаётся по содержимому: короткий текст — компактный
    пузырь, длинный текст — широкий (до предела ширины чата). Это позволяет
    длинным фразам занимать больше горизонтального пространства, а не
    вытягиваться в узкий столбик.
    """

    _PAD = 32  # padding 15×2 + border 2

    def __init__(self, text, role, parent=None):
        super().__init__(text, parent)
        self._role = role
        self._max_width = 220
        self.setWordWrap(True)
        self.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Minimum,
        )
        self._apply_style()

    def _apply_style(self):
        if self._role == "user":
            bg = BUBBLE_USER_BG
            border = BUBBLE_USER_BORDER
            color = BUBBLE_USER_TEXT
        else:
            bg = BUBBLE_AKIRA_BG
            border = BUBBLE_AKIRA_BORDER
            color = BUBBLE_AKIRA_TEXT

        rgba = lambda c: f"rgba({c.red()}, {c.green()}, {c.blue()}, {c.alpha()})"
        self.setStyleSheet(
            f"QLabel {{ background: {rgba(bg)}; color: {color.name()}; "
            f"border: 1px solid {rgba(border)}; border-radius: 15px; "
            f"padding: 10px 15px; font-size: 13px; line-height: 1.35; }}"
        )

    def _natural_width(self):
        metrics = self.fontMetrics()
        return metrics.horizontalAdvance(self.text()) + self._PAD

    def set_max_width(self, max_width):
        """Обновляет допустимую ширину и пересчитывает размер пузыря."""
        self._max_width = max_width
        self.setFixedWidth(min(self._natural_width(), max_width))


class MessageRow(QWidget):
    """Ряд одного сообщения: bubble слева (Akira) или справа (user)."""

    def __init__(self, text, role, max_width, parent=None):
        super().__init__(parent)
        self._bubble = Bubble(text, role, self)
        self._bubble.set_max_width(max_width)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        if role == "user":
            layout.addStretch(1)
            layout.addWidget(self._bubble)
        else:
            layout.addWidget(self._bubble)
            layout.addStretch(1)

    def set_max_width(self, width):
        self._bubble.set_max_width(width)


class ChatView(QScrollArea):
    """История чата с bubble-сообщениями и тонким интегрированным скроллбаром.

    Автоскролл: при новом сообщении прокручивается вниз, только если
    пользователь уже был внизу; ручная прокрутка вверх отключает автоскролл,
    возвращение вниз — включает снова.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollArea > QWidget > QWidget { background: transparent; }"
            "QScrollBar:vertical { background: transparent; width: 5px; "
            "margin: 2px 1px 2px 0; border: none; }"
            "QScrollBar::handle:vertical { background: rgba(255, 70, 88, 42); "
            "border-radius: 2px; min-height: 26px; }"
            "QScrollBar::handle:vertical:hover { background: rgba(255, 70, 88, 120); }"
            "QScrollBar::handle:vertical:pressed { background: rgba(255, 70, 88, 180); }"
            "QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }"
            "QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }"
        )

        self._rows = []
        self._stick_to_bottom = True

        self._container = QWidget(self)
        self._layout = QVBoxLayout(self._container)
        self._layout.setContentsMargins(0, 0, 8, 0)
        self._layout.setSpacing(7)
        self._layout.addStretch(1)
        self.setWidget(self._container)

        bar = self.verticalScrollBar()
        bar.valueChanged.connect(self._on_scroll)
        bar.rangeChanged.connect(self._on_range_changed)

    def _max_row_width(self):
        return max(220, int(self.viewport().width() * 0.92))

    def add_message(self, text, role):
        row = MessageRow(text, role, self._max_row_width(), self._container)
        self._rows.append(row)
        self._layout.insertWidget(self._layout.count() - 1, row)
        self._scroll_to_bottom_if_stuck()

    def _scroll_to_bottom_if_stuck(self):
        if self._stick_to_bottom:
            bar = self.verticalScrollBar()
            bar.setValue(bar.maximum())

    def _on_scroll(self, value):
        bar = self.verticalScrollBar()
        if value >= bar.maximum() - 6:
            self._stick_to_bottom = True
        else:
            self._stick_to_bottom = False

    def _on_range_changed(self, _min, _max):
        self._scroll_to_bottom_if_stuck()

    def resizeEvent(self, event):
        width = self._max_row_width()
        for row in self._rows:
            row.set_max_width(width)
        super().resizeEvent(event)


class MessageEdit(QTextEdit):
    """Многострочный ввод: Enter отправляет, Shift+Enter — перенос.

    Поле растёт до разумного максимума, затем скроллится внутри.
    """

    submitted = Signal(str)

    MIN_HEIGHT = 42
    MAX_HEIGHT = 120

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptRichText(False)
        self.setTabChangesFocus(True)
        self.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.setPlaceholderText("Напишите сообщение...")
        self.setFixedHeight(self.MIN_HEIGHT)
        self.document().contentsChanged.connect(self._auto_resize)

    def _auto_resize(self):
        doc_height = int(self.document().size().height())
        target = min(self.MAX_HEIGHT, max(self.MIN_HEIGHT, doc_height + 18))
        if target != self.height():
            self.setFixedHeight(target)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if not (event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
                text = self.toPlainText().strip()
                if text:
                    self.submitted.emit(text)
                    self.clear()
                    self._auto_resize()
                event.accept()
                return
        super().keyPressEvent(event)


class MicButton(QWidget):
    """Круглая toggle-кнопка микрофона с плавным переходом OFF/ON.

    Состояние полностью управляется сигналом mic_capture движка:
    активна ровно пока идёт запись, и не более.
    """

    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(46, 46)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._active = False
        self._glow = 0.0
        self._hover = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(16)

    def set_active(self, active):
        if active != self._active:
            self._active = active
            self.update()

    def is_active(self):
        return self._active

    def _tick(self):
        target = 1.0 if self._active else 0.0
        self._glow += (target - self._glow) * 0.14
        if self._glow < 0.01:
            self._glow = 0.0
        self.update()

    def enterEvent(self, event):
        self._hover = 1.0
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover = 0.0
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        cx, cy = w / 2.0, h / 2.0
        radius = w / 2.0 - 2

        glow = self._glow
        hover = self._hover

        # Мягкое красное свечение вокруг активной кнопки.
        if glow > 0.01:
            outer = QColor(255, 60, 75, int(70 * glow))
            painter.setBrush(outer)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(QPointF(cx, cy), radius + 7 * glow, radius + 7 * glow)

        # Фон кнопки: тёмный → красный в активном состоянии.
        if glow > 0.01:
            bg = QColor(
                int(28 + 88 * glow),
                int(22 + 12 * glow),
                int(28 + 18 * glow),
                255,
            )
        else:
            bg = QColor(24, 24, 30, 255)

        painter.setBrush(bg)
        border_color = QColor(
            int(52 + 120 * glow + 18 * hover),
            int(50 + 18 * glow + 14 * hover),
            int(60 + 22 * glow + 14 * hover),
            255,
        )
        painter.setPen(QPen(border_color, 1.5))
        painter.drawEllipse(QPointF(cx, cy), radius, radius)

        # Иконка микрофона.
        if glow > 0.45:
            icon = QColor(255, 216, 220, 255)
        else:
            icon = QColor(158, 158, 170, 255)

        painter.setPen(QPen(icon, 2.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.setBrush(Qt.BrushStyle.NoBrush)

        # Цельный микрофон: капсула опирается на U-чашку, из которой
        # без разрыва выходит стойка, уходящая в основание.
        #
        #   [капсула]
        #     |  |
        #     \__/   <- U-чашка
        #      |
        #   основание
        #
        # Капсула и чашка рисуются так, чтобы их нижние границы совпадали,
        # а стойка начинается прямо из дна чашки — никаких визуальных
        # разрывов между корпусом, ножкой и основанием.

        # Капсула (корпус микрофона). Нижний край — на cy+0.5.
        body = QRectF(cx - 4.2, cy - 12.5, 8.4, 13.0)
        painter.drawRoundedRect(body, 4.2, 4.2)

        # U-чашка: дуга, чьи верхние края находятся ровно на нижнем крае
        # капсулы, а дно уходит вниз — капсула «сидит» в чашке без зазора.
        painter.drawArc(
            QRectF(cx - 8.5, cy - 7.0, 17.0, 15.0),
            180 * 16,
            180 * 16,
        )

        # Стойка: прямо из дна чашки (cy+8.0) к основанию (cy+12.5).
        painter.drawLine(QPointF(cx, cy + 8.0), QPointF(cx, cy + 12.5))

        # Основание.
        painter.drawLine(QPointF(cx - 6.0, cy + 12.5), QPointF(cx + 6.0, cy + 12.5))


class ConfirmationDialog(QDialog):
    """Тёмная карточка подтверждения действия Акиры."""

    def __init__(self, description, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Akira")
        self.setModal(True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.resize(420, 220)

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 28, 28, 24)
        root.setSpacing(18)

        title = QLabel("Akira хочет выполнить действие", self)
        title.setStyleSheet(
            "color: #e8e8ee; font-size: 15px; font-weight: 600;"
        )

        desc = QLabel(description, self)
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #b8b8c2; font-size: 14px;")

        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        buttons.addStretch(1)

        cancel = QPushButton("Отмена", self)
        cancel.setStyleSheet(
            "QPushButton { background: rgba(255,255,255,14); color: #c8c8d0; "
            "border: 1px solid #3a3a44; border-radius: 10px; "
            "padding: 8px 18px; font-size: 14px; }"
            "QPushButton:hover { background: rgba(255,255,255,22); }"
        )
        cancel.clicked.connect(self.reject)

        allow = QPushButton("Разрешить", self)
        allow.setStyleSheet(
            "QPushButton { background: #ff3c4b; color: #ffffff; "
            "border: none; border-radius: 10px; padding: 8px 18px; "
            "font-size: 14px; font-weight: 600; }"
            "QPushButton:hover { background: #ff5763; }"
        )
        allow.setDefault(True)
        allow.clicked.connect(self.accept)

        buttons.addWidget(cancel)
        buttons.addWidget(allow)

        root.addWidget(title)
        root.addWidget(desc)
        root.addLayout(buttons)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor(60, 60, 74, 230), 1))
        painter.setBrush(QColor(20, 20, 25, 252))
        painter.drawRoundedRect(self.rect(), 16, 16)


class MainWindow(QWidget):
    """Компактное тёмное окно ~700x700 с бионической сферой."""

    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"
    CONFIRMING = "confirming"
    DISABLED = "disabled"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._dialog = None
        self._drag_pos = None
        self._last_voice = False
        self._state = self.IDLE
        self._mic_active = False

        self.confirmation = ConfirmationService(self)
        self.voice = VoiceEngine(wake_enabled=True, parent=self)
        self.worker = BrainWorker(session_id="desktop", parent=self)

        # voice.dialogue устанавливает deny_all при импорте; переопределяем
        # провайдер подтверждения после всех импортов.
        from permissions import set_confirmation_provider

        set_confirmation_provider(self.confirmation.provider)

        self._menu = QMenu(self)
        self._action_wake = self._menu.addAction("Wake word: «Акира»")
        self._action_wake.setCheckable(True)
        self._action_wake.setChecked(True)
        self._action_wake.toggled.connect(self._on_wake_toggled)
        self._menu.addSeparator()
        self._menu.addAction("Закрыть", self.close)

        self._build_ui()
        self._connect()

        self.setWindowTitle("Akira")
        self.resize(700, 700)

        self.voice.start()
        self.worker.start()

        if not os.environ.get("GROQ_API_KEY"):
            self._show_error("Не найден GROQ_API_KEY. Проверь настройки API.")
            self._set_state(self.DISABLED)

    # ------------------------------------------------------------ UI build
    def _build_ui(self):
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_title_bar())
        root.addWidget(self._build_content(), 1)

    def _build_title_bar(self):
        bar = QWidget(self)
        bar.setFixedHeight(48)

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(16, 12, 16, 8)
        layout.setSpacing(8)

        lights = QWidget(bar)
        lights_layout = QHBoxLayout(lights)
        lights_layout.setContentsMargins(0, 0, 0, 0)
        lights_layout.setSpacing(8)
        lights_layout.addWidget(
            TrafficLight("#ff5f57", self.close, lights)
        )
        lights_layout.addWidget(
            TrafficLight("#febc2e", self.showMinimized, lights)
        )
        lights_layout.addWidget(
            TrafficLight("#28c840", self._toggle_zoom, lights)
        )
        layout.addWidget(lights)

        title = QLabel("Akira", bar)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            "color: #d8d8e0; font-size: 14px; font-weight: 600;"
            "background: transparent; border: none;"
        )
        layout.addWidget(title, 1)

        gear = QToolButton(bar)
        gear.setText("•••")
        gear.setCursor(Qt.CursorShape.PointingHandCursor)
        gear.setStyleSheet(
            "QToolButton { color: #76767f; font-size: 12px; border: none; "
            "background: transparent; padding: 2px 4px; }"
            "QToolButton:hover { color: #d8d8e0; }"
        )
        gear.setMenu(self._menu)
        gear.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        layout.addWidget(gear)

        return bar

    def _build_content(self):
        content = QWidget(self)

        layout = QVBoxLayout(content)
        layout.setContentsMargins(34, 10, 34, 22)
        layout.setSpacing(10)

        self.visualizer = HalftoneWidget(content)
        self.visualizer.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        layout.addWidget(self.visualizer, 1)

        self.status = QLabel("", content)
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status.setStyleSheet(
            "color: #9696a0; font-size: 12px; background: transparent;"
        )
        self.status.setFixedHeight(18)
        layout.addWidget(self.status)

        self._messages_area = ChatView(content)
        self._messages_area.setFixedHeight(190)
        self._messages_area.setVisible(False)
        layout.addWidget(self._messages_area)

        layout.addWidget(self._build_input_row())

        return content

    def _build_input_row(self):
        row = QWidget(self)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self.input = MessageEdit(row)
        self.input.setStyleSheet(
            f"QTextEdit {{ background: rgba({INPUT_BG.red()}, {INPUT_BG.green()}, "
            f"{INPUT_BG.blue()}, {INPUT_BG.alpha()}); color: #e8e8ee; "
            f"border: 1px solid rgba({INPUT_BORDER.red()}, {INPUT_BORDER.green()}, "
            f"{INPUT_BORDER.blue()}, {INPUT_BORDER.alpha()}); "
            f"border-radius: 21px; padding: 8px 16px; font-size: 14px; }}"
            f"QTextEdit:focus {{ border: 1px solid rgba(255, 60, 75, 140); }}"
            f"QTextEdit::placeholder {{ color: #6a6a74; }}"
        )
        layout.addWidget(self.input, 1)

        self.mic_button = MicButton(row)
        layout.addWidget(self.mic_button)

        return row

    def _connect(self):
        self.worker.answer_ready.connect(self._on_answer)
        self.worker.error.connect(self._on_error)
        self.worker.activity.connect(self._on_activity)
        self.worker.busy.connect(self._on_busy)

        self.voice.text_ready.connect(self._on_voice_text)
        self.voice.state_changed.connect(self._on_voice_state)
        self.voice.error.connect(self._on_error)
        self.voice.mic_capture.connect(self._on_mic_capture)
        self.voice.dialogue_changed.connect(self._on_dialogue_changed)

        self.confirmation.request_received.connect(self._on_confirmation)

        self.visualizer.clicked.connect(self._on_sphere_clicked)
        self.input.submitted.connect(self._on_submit)
        self.mic_button.clicked.connect(self._on_mic_clicked)

    def _on_wake_toggled(self, enabled):
        self.voice.set_wake_enabled(enabled)

    def _toggle_zoom(self):
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    # ------------------------------------------------------------ messages
    def _append_message(self, text, role):
        if not text:
            return

        self._messages_area.add_message(text, role)
        self._messages_area.setVisible(True)

    def _show_error(self, message):
        self.status.setText(message)
        self.status.setStyleSheet(
            "color: #ff8a8a; font-size: 12px; background: transparent;"
        )

    def _clear_status(self):
        self.status.setText("")
        self.status.setStyleSheet(
            "color: #9696a0; font-size: 12px; background: transparent;"
        )

    # ------------------------------------------------------------ state
    def _set_state(self, state):
        if state == self._state:
            return
        self._state = state

        if state == self.IDLE:
            self.visualizer.set_state(HalftoneWidget.IDLE)
            self.input.setEnabled(True)
        elif state == self.LISTENING:
            self.visualizer.set_state(HalftoneWidget.LISTENING)
        elif state == self.THINKING:
            self.visualizer.set_state(HalftoneWidget.THINKING)
            self.input.setEnabled(False)
        elif state == self.SPEAKING:
            self.visualizer.set_state(HalftoneWidget.SPEAKING)
            self.input.setEnabled(False)
        elif state == self.CONFIRMING:
            self.visualizer.set_state(HalftoneWidget.THINKING)
            self.input.setEnabled(False)
        elif state == self.DISABLED:
            self.visualizer.set_state(HalftoneWidget.DISABLED)
            self.input.setEnabled(False)
            self.mic_button.set_active(False)

    # ------------------------------------------------------------ events
    def _on_submit(self, message):
        self._append_message(message, "user")
        self._last_voice = False
        self.voice.pause()
        self.worker.submit(message)
        self._set_state(self.THINKING)

    def _on_voice_text(self, text):
        if not text:
            return
        self._append_message(text, "user")
        self._last_voice = True
        self.voice.pause()
        self.worker.submit(text)
        self._set_state(self.THINKING)

    def _on_answer(self, answer):
        if not answer:
            answer = "Готово."
        self._append_message(answer, "akira")
        self._clear_status()

        if self._last_voice:
            self._set_state(self.SPEAKING)
            self.voice.speak(answer)
        elif self.voice.is_dialogue():
            self._set_state(self.LISTENING)
            self.voice.resume()
        else:
            self._set_state(self.IDLE)

    def _on_error(self, message):
        self._show_error(message)
        self._set_state(self.IDLE)
        if self.voice.is_dialogue():
            self.voice.resume()

    def _on_activity(self, label):
        self.status.setText(label)
        self.status.setStyleSheet(
            "color: #c0c0c8; font-size: 12px; background: transparent;"
        )

    def _on_busy(self, busy):
        if not busy:
            if self._state not in (self.LISTENING, self.SPEAKING):
                self._set_state(self.IDLE)

    def _on_voice_state(self, state):
        if state == VoiceEngine.LISTENING:
            self._set_state(self.LISTENING)
        elif state == VoiceEngine.SPEAKING:
            self._set_state(self.SPEAKING)
        elif state == VoiceEngine.THINKING:
            self._set_state(self.THINKING)
        elif state == VoiceEngine.IDLE:
            if self._state == self.SPEAKING:
                # TTS завершён.
                if self.voice.is_dialogue():
                    self._set_state(self.LISTENING)
                else:
                    self._set_state(self.IDLE)
            elif self._state == self.LISTENING and self.voice.is_dialogue():
                # Пауза между фразами диалога.
                pass
            elif not self.worker.isRunning():
                self._set_state(self.IDLE)

    def _on_mic_capture(self, active):
        self._mic_active = active
        self.mic_button.set_active(active)

    def _on_dialogue_changed(self, enabled):
        self.visualizer.set_dialogue(enabled)

    def _on_sphere_clicked(self):
        if self._state in (self.THINKING, self.SPEAKING, self.DISABLED):
            return
        enabled = not self.voice.is_dialogue()
        self.voice.set_dialogue(enabled)
        if enabled:
            self._set_state(self.LISTENING)
            self.voice.resume()
        else:
            self.voice.pause()
            self._set_state(self.IDLE)
            self._clear_status()

    def _on_mic_clicked(self):
        if self._state in (self.SPEAKING, self.DISABLED):
            if self._state == self.SPEAKING:
                # Прерываем озвучку.
                self.voice.stop_speaking()
                self._set_state(self.IDLE)
            return
        if self._state == self.THINKING:
            return
        if self._mic_active:
            # Выключение: отменяем текущую запись.
            self.voice.cancel_capture()
            self._set_state(self.IDLE)
            return
        # Включение: разовое распознавание.
        self.voice.capture_once()

    def _on_confirmation(self, tool_name, description, arguments, request):
        self._set_state(self.CONFIRMING)
        dialog = ConfirmationDialog(description, self)
        request["allowed"] = dialog.exec() == QDialog.DialogCode.Accepted
        request["answered"].set()

        if self._state == self.CONFIRMING:
            self._set_state(self.THINKING)

    # ------------------------------------------------------------ painting
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(BORDER, 1))
        painter.setBrush(BACKGROUND)
        painter.drawRoundedRect(self.rect(), 20, 20)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and event.position().y() < 48:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_pos = None

    def closeEvent(self, event):
        self.voice.stop()
        self.worker.request_stop()
        self.worker.wait(5000)
        super().closeEvent(event)