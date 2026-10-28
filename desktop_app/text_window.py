"""Stable text-only desktop surface for Akira.

This surface deliberately has no dependency on the voice runtime. Text input
is owned by the Qt window and requests are serialized by BrainWorker.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .worker import BrainWorker
from .confirmation import ConfirmationService


class TextChatView(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self._container = QWidget()
        self._container.setStyleSheet("background:#101013;")
        self._layout = QVBoxLayout(self._container)
        self._layout.setContentsMargins(20, 20, 20, 12)
        self._layout.setSpacing(10)
        self._layout.addStretch(1)
        self.setWidget(self._container)

    def add_message(self, text: str, role: str):
        label = QLabel(str(text))
        label.setTextFormat(Qt.TextFormat.PlainText)
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        label.setMaximumWidth(760)
        if role == "user":
            label.setStyleSheet(
                "QLabel { background:#7e1626; color:#fff; border-radius:14px; padding:10px 14px; }"
            )
            row = QHBoxLayout()
            row.addStretch(1)
            row.addWidget(label)
        else:
            label.setStyleSheet(
                "QLabel { background:#1e1e24; color:#e4e4ec; border:1px solid #303038; border-radius:14px; padding:10px 14px; }"
            )
            row = QHBoxLayout()
            row.addWidget(label)
            row.addStretch(1)
        row.setContentsMargins(0, 0, 0, 0)
        wrapper = QWidget()
        wrapper.setLayout(row)
        self._layout.insertWidget(self._layout.count() - 1, wrapper)
        self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())


class TextInput(QPlainTextEdit):
    def __init__(self, window, parent=None):
        super().__init__(parent)
        self._window = window
        self.setPlaceholderText("Напишите сообщение...")
        self.setFixedHeight(52)
        self.setTabChangesFocus(True)
        self.setStyleSheet(
            "QPlainTextEdit { background:#16161b; color:#e8e8ee; border:1px solid #303038; "
            "border-radius:12px; padding:10px; }"
        )

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not (
            event.modifiers() & Qt.KeyboardModifier.ShiftModifier
        ):
            self._window.submit_current()
            event.accept()
            return
        super().keyPressEvent(event)


class TextMainWindow(QMainWindow):
    """Canonical desktop surface while voice is disabled."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._closing = False
        self._confirmation_dialog = None
        self._confirmation_request = None
        self.setWindowTitle("Akira")
        self.resize(860, 700)
        self.setStyleSheet("QMainWindow { background:#101013; }")

        root = QWidget(self)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QLabel("AKIRA")
        header.setFont(QFont("SF Pro Display", 16, QFont.Weight.DemiBold))
        header.setStyleSheet("color:#e8e8ee; padding:16px 20px;")
        layout.addWidget(header)

        self.chat = TextChatView()
        layout.addWidget(self.chat, 1)

        bottom = QWidget()
        bottom_layout = QHBoxLayout(bottom)
        bottom_layout.setContentsMargins(20, 10, 20, 20)
        bottom_layout.setSpacing(10)
        self.input = TextInput(self)
        self.send = QPushButton("Отправить")
        self.send.setFixedWidth(110)
        self.send.clicked.connect(self.submit_current)
        self.send.setStyleSheet(
            "QPushButton { background:#7e1626; color:white; border:0; border-radius:10px; padding:10px; }"
            "QPushButton:disabled { background:#3a2228; color:#999; }"
        )
        self.stop = QPushButton("Остановить")
        self.stop.setStyleSheet(
            "QPushButton { background:#25252d; color:#e8e8ee; border:1px solid #393941; "
            "border-radius:10px; padding:10px; }"
            "QPushButton:disabled { color:#777; }"
        )
        self.stop.setEnabled(False)
        self.stop.clicked.connect(self._cancel_current)
        bottom_layout.addWidget(self.input, 1)
        bottom_layout.addWidget(self.send)
        bottom_layout.addWidget(self.stop)
        layout.addWidget(bottom)

        self.setCentralWidget(root)
        from permissions import set_confirmation_provider
        self.confirmation = ConfirmationService(self)
        self.confirmation.request_received.connect(self._on_confirmation)
        set_confirmation_provider(self.confirmation.provider)
        self.worker = BrainWorker(session_id="desktop")
        self.worker.answer_ready.connect(self._on_answer)
        self.worker.error.connect(self._on_error)
        self.worker.busy.connect(self._on_busy)
        self.worker.finished.connect(self._on_worker_finished)
        self.worker.start()
        self.input.setFocus()

    def submit_current(self):
        text = self.input.toPlainText().strip()
        if not text:
            return
        self.input.clear()
        self.chat.add_message(text, "user")
        if self.worker._stop_word(text):
            self._cancel_current()
            return
        self.worker.submit(text)

    def _on_busy(self, busy: bool):
        self.stop.setEnabled(busy and not self._closing)
        if not busy and self._confirmation_dialog is not None:
            self._confirmation_dialog.reject()

    def _cancel_current(self):
        if self.worker.cancel_current():
            self.chat.add_message("Остановил.", "akira")
        if self._confirmation_dialog is not None:
            self._confirmation_dialog.reject()

    def _on_confirmation(self, tool_name, description, arguments, request):
        if self._closing or self._confirmation_dialog is not None or request["answered"].is_set():
            request["answered"].set()
            return
        dialog = QMessageBox(self)
        dialog.setWindowTitle("Разрешить действие?")
        dialog.setTextFormat(Qt.TextFormat.PlainText)
        dialog.setText(description)
        dialog.setDetailedText(str(arguments))
        dialog.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        dialog.setDefaultButton(QMessageBox.StandardButton.No)
        self._confirmation_dialog = dialog
        self._confirmation_request = request

        def finish(result):
            if not request["answered"].is_set():
                request["allowed"] = result == QMessageBox.StandardButton.Yes
                request["answered"].set()
            self._confirmation_dialog = None
            self._confirmation_request = None
            dialog.deleteLater()

        dialog.finished.connect(finish)
        timer = QTimer(dialog)
        timer.setInterval(100)
        timer.timeout.connect(lambda: dialog.reject() if request["answered"].is_set() else None)
        timer.start()
        # Keep Stop and window close available while permission is pending.
        dialog.setWindowModality(Qt.WindowModality.NonModal)
        dialog.show()

    def _on_worker_finished(self):
        if self._closing:
            QTimer.singleShot(0, self.close)

    def _on_answer(self, answer: str):
        self.chat.add_message(answer, "akira")
        self.input.setEnabled(True)
        self.send.setEnabled(True)
        self.input.setFocus()

    def _on_error(self, message: str):
        self.chat.add_message(message, "akira")
        self.input.setEnabled(True)
        self.send.setEnabled(True)
        self.input.setFocus()

    def closeEvent(self, event):
        self._closing = True
        self.input.setEnabled(False)
        self.send.setEnabled(False)
        self.stop.setEnabled(False)
        if self._confirmation_dialog is not None:
            self._confirmation_dialog.reject()
        self.worker.request_stop()
        if self.worker.isRunning():
            # Keep the QThread owner alive until any in-flight call returns.
            event.ignore()
            return
        from permissions import deny_all, set_confirmation_provider
        set_confirmation_provider(deny_all)
        super().closeEvent(event)
