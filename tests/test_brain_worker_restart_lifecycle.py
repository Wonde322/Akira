import queue

import pytest


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _drain(worker):
    items = []
    while True:
        try:
            items.append(worker._queue.get_nowait())
        except queue.Empty:
            return items


def test_prepare_start_clears_stop_flag(qapp):
    from desktop_app.worker import BrainWorker

    worker = BrainWorker()
    worker.request_stop()
    assert worker._stop is True

    worker._prepare_start()

    assert worker._stop is False


def test_prepare_start_discards_stale_stop_sentinel(qapp):
    from desktop_app.worker import BrainWorker

    worker = BrainWorker()
    worker.request_stop()
    worker._prepare_start()

    assert _drain(worker) == []


def test_prepare_start_preserves_message_queued_before_start(qapp):
    from desktop_app.worker import BrainWorker

    worker = BrainWorker()
    worker.submit("первая команда")
    worker._prepare_start()

    assert _drain(worker) == ["первая команда"]


def test_prepare_start_preserves_multiple_messages(qapp):
    from desktop_app.worker import BrainWorker

    worker = BrainWorker()
    worker.submit("первая")
    worker.submit("вторая")
    worker.request_stop()
    worker._prepare_start()

    assert _drain(worker) == ["первая", "вторая"]


def test_prepare_start_removes_only_none_sentinels(qapp):
    from desktop_app.worker import BrainWorker

    worker = BrainWorker()
    worker._queue.put(None)
    worker.submit("команда")
    worker._queue.put(None)
    worker._prepare_start()

    assert _drain(worker) == ["команда"]


def test_submit_none_cannot_inject_shutdown_sentinel(qapp):
    from desktop_app.worker import BrainWorker

    worker = BrainWorker()
    worker.submit(None)

    assert _drain(worker) == []


def test_prepare_start_is_idempotent(qapp):
    from desktop_app.worker import BrainWorker

    worker = BrainWorker()
    worker.submit("команда")
    worker._prepare_start()
    worker._prepare_start()

    assert worker._stop is False
    assert _drain(worker) == ["команда"]


def test_stop_then_prepare_start_keeps_session(qapp):
    from desktop_app.worker import BrainWorker

    worker = BrainWorker(session_id="desktop-test")
    worker.request_stop()
    worker._prepare_start()

    assert worker.session_id == "desktop-test"
    assert worker._stop is False
