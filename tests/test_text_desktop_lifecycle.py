import threading
import time

import pytest
from PySide6.QtWidgets import QMessageBox


def wait_until(qapp, predicate, timeout=2):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        qapp.processEvents()
        if predicate():
            return
        time.sleep(0.005)
    assert predicate()


@pytest.fixture
def window(qapp, monkeypatch):
    from desktop_app.worker import BrainWorker
    from desktop_app.text_window import TextMainWindow

    monkeypatch.setattr(BrainWorker, "start", lambda self: None)
    window = TextMainWindow()
    yield window
    window.close()
    qapp.processEvents()


def test_busy_window_keeps_stop_and_input_available(window):
    window._on_busy(True)
    assert window.input.isEnabled()
    assert window.send.isEnabled()
    assert window.stop.isEnabled()


def test_stop_word_uses_cancellation_without_queuing(window):
    cancelled = []
    window.worker._active_request_id = "request"
    window.worker._gateway = type("Gateway", (), {"cancel": lambda self, request_id: cancelled.append(request_id)})()
    window.input.setPlainText("стоп")
    window.submit_current()
    assert cancelled == ["request"]
    assert window.worker._queue.empty()


@pytest.mark.parametrize("choice,allowed", [(QMessageBox.StandardButton.Yes, True), (QMessageBox.StandardButton.No, False)])
def test_text_confirmation_is_connected_to_permission_provider(window, qapp, choice, allowed):
    from permissions import request_confirmation

    def answer():
        dialog = window._confirmation_dialog
        assert dialog is not None
        assert not dialog.isModal()
        dialog.done(choice)

    # The provider normally runs in the worker; pump UI events while it waits.
    result = []
    thread = threading.Thread(target=lambda: result.append(request_confirmation("delete", {"path": "test.txt"})))
    thread.start()
    try:
        wait_until(qapp, lambda: window._confirmation_dialog is not None)
        answer()
        thread.join(1)
        assert result == [allowed]
    finally:
        if window._confirmation_dialog is not None:
            window._confirmation_dialog.reject()
        thread.join(1)


def test_chat_treats_model_output_as_plain_text(window):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QLabel

    window.chat.add_message('<a href="file:///tmp">test</a>', "akira")
    labels = window.chat.findChildren(QLabel)
    assert labels[-1].textFormat() == Qt.TextFormat.PlainText


def test_close_waits_for_inflight_worker_instead_of_destroying_qthread(window, monkeypatch):
    from PySide6.QtGui import QCloseEvent

    monkeypatch.setattr(window.worker, "isRunning", lambda: True)
    event = QCloseEvent()
    window.closeEvent(event)
    assert not event.isAccepted()
    assert window._closing
    assert not window.input.isEnabled()
    monkeypatch.setattr(window.worker, "isRunning", lambda: False)


def test_real_worker_serializes_requests_and_restarts(qapp):
    from desktop_app.worker import BrainWorker

    class Gateway:
        def __init__(self):
            self.calls = []

        def submit_text(self, message, **kwargs):
            self.calls.append((message, kwargs["request_id"]))
            return message

    worker = BrainWorker()
    worker._gateway = Gateway()
    answers = []
    worker.answer_ready.connect(answers.append)
    worker.submit("one")
    worker.submit("two")
    worker.start()
    try:
        wait_until(qapp, lambda: answers == ["one", "two"])
        worker.request_stop()
        assert worker.wait(1000)
        worker.start()
        worker.submit("three")
        wait_until(qapp, lambda: answers == ["one", "two", "three"])
        ids = [item[1] for item in worker._gateway.calls]
        assert len(ids) == len(set(ids)) == 3
    finally:
        worker.request_stop()
        assert worker.wait(1000)


def test_cancel_hides_late_provider_errors_and_allows_next_request(qapp):
    from desktop_app.worker import BrainWorker

    entered = threading.Event()
    released = threading.Event()

    class Gateway:
        def submit_text(self, message, **kwargs):
            if message == "slow":
                entered.set()
                assert released.wait(2)
                raise RuntimeError("late network error")
            return message

        def cancel(self, request_id):
            released.set()
            return True

    worker = BrainWorker()
    worker._gateway = Gateway()
    answers, errors = [], []
    worker.answer_ready.connect(answers.append)
    worker.error.connect(errors.append)
    worker.submit("slow")
    worker.start()
    try:
        wait_until(qapp, entered.is_set)
        assert worker.cancel_current()
        worker.submit("next")
        wait_until(qapp, lambda: answers == ["next"])
        assert errors == []
    finally:
        released.set()
        worker.request_stop()
        assert worker.wait(1000)


def test_cancel_dismisses_permission_wait_before_timeout(qapp):
    from desktop_app.confirmation import ConfirmationService
    from execution_context import ExecutionContext, activate_execution, deactivate_execution

    service = ConfirmationService(timeout=10)
    requests = []
    service.request_received.connect(lambda tool, description, args, request: requests.append(request))
    cancel = threading.Event()
    results = []

    def ask_permission():
        token = activate_execution(ExecutionContext("test", "test", "auto", _cancel_event=cancel))
        try:
            results.append(service.provider("delete", {"path": "test.txt"}))
        finally:
            deactivate_execution(token)

    thread = threading.Thread(target=ask_permission)
    thread.start()
    try:
        wait_until(qapp, lambda: len(requests) == 1)
        cancel.set()
        thread.join(1)
        assert results == [False]
        assert requests[0]["answered"].is_set()
    finally:
        cancel.set()
        thread.join(1)


def test_expired_confirmation_cannot_be_approved_later(window, qapp):
    request = {"allowed": False, "answered": threading.Event()}
    request["answered"].set()
    window._on_confirmation("delete", "Удалить", {}, request)
    assert window._confirmation_dialog is None
    assert request["allowed"] is False
