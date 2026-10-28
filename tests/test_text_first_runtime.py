from __future__ import annotations


def test_worker_normal_submissions_keep_fifo_request_identity():
    from desktop_app.worker import BrainWorker

    worker = BrainWorker()
    worker.submit("первый")
    worker.submit("второй")
    first = worker._queue.get_nowait()
    second = worker._queue.get_nowait()
    assert [first[0], second[0]] == ["первый", "второй"]
    assert first[1] != second[1]


def test_worker_cancellation_invalidates_only_active_request():
    from desktop_app.worker import BrainWorker

    class Gateway:
        def cancel(self, request_id):
            assert request_id == "active"
            return True

    worker = BrainWorker()
    worker._gateway = Gateway()
    worker._active_request_id = "active"
    worker.submit("следующий")
    assert worker.cancel_current()
    assert worker._active_request_id is None
    assert worker._queue.get_nowait()[0] == "следующий"
    assert not worker.cancel_current()


def test_text_window_does_not_import_voice_runtime():
    import sys

    sys.modules.pop("desktop_app.text_window", None)
    sys.modules.pop("desktop_app.voice", None)
    import desktop_app.text_window  # noqa: F401
    assert "desktop_app.voice" not in sys.modules
