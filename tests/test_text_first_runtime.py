from __future__ import annotations


def test_worker_normal_submissions_keep_fifo_generation():
    from desktop_app.worker import BrainWorker

    worker = BrainWorker()
    worker.submit("первый")
    worker.submit("второй")

    first = worker._queue.get_nowait()
    second = worker._queue.get_nowait()

    assert first == ("первый", second[1])
    assert second == ("второй", first[1])


def test_worker_cancellation_invalidates_existing_generation_only():
    from desktop_app.worker import BrainWorker

    worker = BrainWorker()
    worker.submit("первый")
    before = worker._queue.get_nowait()
    worker.cancel_current()
    worker.submit("второй")
    after = worker._queue.get_nowait()

    assert before[1] != after[1]


def test_text_window_does_not_import_voice_runtime(monkeypatch):
    import sys

    sys.modules.pop("desktop_app.text_window", None)
    sys.modules.pop("desktop_app.voice", None)

    import desktop_app.text_window  # noqa: F401

    assert "desktop_app.voice" not in sys.modules
