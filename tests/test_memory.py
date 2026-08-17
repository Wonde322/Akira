import json
from datetime import timedelta

import pytest


def test_missing_memory_file_returns_the_documented_base_schema(isolated_project):
    memory = isolated_project("memory")

    loaded = memory.load_memory()

    assert set(loaded) == {
        "goals",
        "tasks",
        "events",
        "activity",
        "facts",
        "preferences",
        "episodes",
        "procedures",
    }

    assert loaded["goals"] == []
    assert loaded["tasks"] == []
    assert loaded["events"] == []
    assert loaded["activity"] == []
    assert loaded["facts"] == []
    assert loaded["preferences"] == []
    assert loaded["episodes"] == []
    assert loaded["procedures"] == []


def test_memory_operations_preserve_existing_record_shapes(isolated_project, tmp_path):
    memory = isolated_project("memory")

    memory.add_goal("Закончить проект")
    memory.add_task("Написать тесты", goal="Закончить проект")
    memory.add_event("Открыл редактор")
    memory.complete_task("тесты")

    stored = json.loads((tmp_path / "memory.json").read_text(encoding="utf-8"))

    assert set(stored) == {
        "goals",
        "tasks",
        "events",
        "activity",
        "facts",
        "preferences",
        "episodes",
        "procedures",
    }
    assert set(stored["goals"][0]) == {"text", "created"}
    assert stored["goals"][0]["text"] == "Закончить проект"
    assert set(stored["tasks"][0]) == {
        "text", "goal", "completed", "created", "completed_at"
    }
    assert stored["tasks"][0]["completed"] is True
    assert set(stored["events"][0]) == {"text", "time"}


def test_activity_is_saved_through_memory_api_without_losing_other_data(
    isolated_project,
):
    memory = isolated_project("memory")

    memory.add_goal("Закончить проект")
    memory.add_task("Написать тесты")
    memory.add_event("Начал работу")
    memory.add_activity_session(
        "Editor",
        "2026-08-13T10:00:00",
        "2026-08-13T10:15:00",
        900,
    )

    stored = memory.load_memory()

    assert [goal["text"] for goal in stored["goals"]] == ["Закончить проект"]
    assert [task["text"] for task in stored["tasks"]] == ["Написать тесты"]
    assert [event["text"] for event in stored["events"]] == ["Начал работу"]
    assert stored["activity"] == [{
        "app": "Editor",
        "started": "2026-08-13T10:00:00",
        "ended": "2026-08-13T10:15:00",
        "duration_seconds": 900,
    }]


def test_activity_selection_and_aggregation_use_memory_api(isolated_project):
    memory = isolated_project("memory")
    now = memory.datetime.now()
    started_at = (now - timedelta(minutes=20)).isoformat(timespec="seconds")
    ended_at = (now - timedelta(minutes=5)).isoformat(timespec="seconds")

    memory.add_activity_session("Editor", started_at, ended_at, 900)

    assert memory.get_activity_for_period(1)[0]["app"] == "Editor"
    assert memory.get_activity_totals(1) == {"Editor": 900}


def test_mutation_reads_current_file_instead_of_using_import_time_snapshot(
    isolated_project, tmp_path
):
    memory = isolated_project("memory")
    (tmp_path / "memory.json").write_text(
        json.dumps({
            "goals": [{"text": "Внешняя цель"}],
            "tasks": [],
            "events": [],
            "activity": [],
        }),
        encoding="utf-8",
    )

    memory.add_event("Новое событие")

    stored = memory.load_memory()
    assert stored["goals"][0]["text"] == "Внешняя цель"
    assert stored["events"][0]["text"] == "Новое событие"


def test_partial_memory_data_receives_safe_defaults(isolated_project, tmp_path):
    memory = isolated_project("memory")
    (tmp_path / "memory.json").write_text(
        json.dumps({
            "goals": [{"text": "Цель"}],
            "tasks": [{"text": "Задача"}],
            "events": [{}],
            "activity": [{}],
        }),
        encoding="utf-8",
    )

    loaded = memory.load_memory()

    assert loaded["goals"][0] == {"text": "Цель", "created": ""}
    assert loaded["tasks"][0] == {
        "text": "Задача",
        "goal": None,
        "completed": False,
        "created": "",
    }
    assert loaded["events"][0] == {"text": "", "time": ""}
    assert loaded["activity"][0] == {
        "app": "Неизвестно",
        "started": "",
        "ended": "",
        "duration_seconds": 0,
    }


def test_corrupted_memory_file_raises_controlled_error(isolated_project, tmp_path):
    memory = isolated_project("memory")
    (tmp_path / "memory.json").write_text("not json", encoding="utf-8")

    with pytest.raises(memory.MemoryCorruptionError, match="повреждён"):
        memory.load_memory()


def test_mutation_does_not_replace_corrupted_memory_file(
    isolated_project, tmp_path
):
    memory = isolated_project("memory")
    memory_path = tmp_path / "memory.json"
    original = "{ invalid json"
    memory_path.write_text(original, encoding="utf-8")

    with pytest.raises(memory.MemoryCorruptionError):
        memory.add_event("Не должно сохраниться")

    assert memory_path.read_text(encoding="utf-8") == original


def test_atomic_save_preserves_existing_file_when_replace_fails(
    isolated_project, monkeypatch, tmp_path
):
    memory = isolated_project("memory")
    memory_path = tmp_path / "memory.json"
    original = '{"goals": ["keep"]}'
    memory_path.write_text(original, encoding="utf-8")

    def fail_replace(source, destination):
        raise OSError("replace failed")

    monkeypatch.setattr(memory.os, "replace", fail_replace)

    with pytest.raises(OSError, match="replace failed"):
        memory.save_memory({"goals": []})

    assert memory_path.read_text(encoding="utf-8") == original
    assert not list(tmp_path.glob(".memory-*.tmp"))


def test_concurrent_memory_updates_do_not_lose_data(isolated_project, tmp_path):
    import threading

    memory = isolated_project("memory")

    def add_event_worker(index):
        memory.add_event(f"Событие {index}")

    threads = [
        threading.Thread(target=add_event_worker, args=(index,))
        for index in range(20)
    ]

    for thread in threads:
        thread.start()

    for thread in threads:
        thread.join()

    stored = memory.load_memory()

    assert len(stored["events"]) == 20
    assert {event["text"] for event in stored["events"]} == {
        f"Событие {index}" for index in range(20)
    }


def test_memory_file_path_is_absolute_and_project_root(monkeypatch, tmp_path):
    import importlib
    import sys
    from pathlib import Path

    sys.modules.pop("memory", None)
    monkeypatch.chdir(tmp_path)

    module = importlib.import_module("memory")

    try:
        assert Path(module.MEMORY_FILE).is_absolute()
        assert Path(module.MEMORY_FILE).parent == Path(__file__).resolve().parents[1]
    finally:
        sys.modules.pop("memory", None)
