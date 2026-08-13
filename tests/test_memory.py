import json


def test_new_memory_has_the_documented_base_schema(isolated_project):
    memory = isolated_project("memory")

    assert memory.load_memory() == {
        "goals": [],
        "tasks": [],
        "events": [],
    }


def test_memory_operations_preserve_existing_record_shapes(isolated_project, tmp_path):
    memory = isolated_project("memory")

    memory.add_goal("Закончить проект")
    memory.add_task("Написать тесты", goal="Закончить проект")
    memory.add_event("Открыл редактор")
    memory.complete_task("тесты")

    stored = json.loads((tmp_path / "memory.json").read_text(encoding="utf-8"))

    assert set(stored) == {"goals", "tasks", "events"}
    assert set(stored["goals"][0]) == {"text", "created"}
    assert stored["goals"][0]["text"] == "Закончить проект"
    assert set(stored["tasks"][0]) == {
        "text", "goal", "completed", "created", "completed_at"
    }
    assert stored["tasks"][0]["completed"] is True
    assert set(stored["events"][0]) == {"text", "time"}


def test_invalid_memory_file_falls_back_to_base_schema(isolated_project, tmp_path):
    memory = isolated_project("memory")
    (tmp_path / "memory.json").write_text("not json", encoding="utf-8")

    assert memory.load_memory() == {
        "goals": [],
        "tasks": [],
        "events": [],
    }
