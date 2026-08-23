import importlib


def test_activity_tracker_import_does_not_start_loop(monkeypatch):
    import activity_tracker

    monkeypatch.setattr(activity_tracker, "run_tracker", lambda: (_ for _ in ()).throw(AssertionError("must not run on import")))
    importlib.reload(activity_tracker)
