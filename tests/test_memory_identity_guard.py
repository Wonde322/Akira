import json

import sitecustomize  # noqa: F401
import memory


def _empty_memory():
    return {
        "goals": [],
        "tasks": [],
        "events": [],
        "activity": [],
        "facts": [],
        "preferences": [],
        "episodes": [],
        "procedures": [],
    }


def test_assistant_name_cannot_be_saved_as_preferred_user_name(monkeypatch, tmp_path):
    path = tmp_path / "memory.json"
    monkeypatch.setattr(memory, "MEMORY_FILE", str(path))

    result = memory.remember_memory(
        content="Акира",
        kind="preference",
        key="preferred_name",
    )

    assert result["success"] is False
    assert result["error"] == "assistant_identity_memory_blocked"
    assert memory.load_memory()["preferences"] == []


def test_assistant_aliases_are_blocked_for_identity_keys(monkeypatch, tmp_path):
    path = tmp_path / "memory.json"
    monkeypatch.setattr(memory, "MEMORY_FILE", str(path))

    for alias in ("Акира", "Akira", "Кира", "Акера"):
        result = memory.remember_memory(
            content=alias,
            kind="preference",
            key="имя пользователя",
        )
        assert result["success"] is False
        assert result["error"] == "assistant_identity_memory_blocked"


def test_real_user_name_is_still_allowed(monkeypatch, tmp_path):
    path = tmp_path / "memory.json"
    monkeypatch.setattr(memory, "MEMORY_FILE", str(path))

    result = memory.remember_memory(
        content="Михаил",
        kind="preference",
        key="preferred_name",
    )

    assert result["success"] is True
    assert memory.load_memory()["preferences"][0]["value"] == "Михаил"


def test_non_identity_memory_about_akira_is_not_blocked(monkeypatch, tmp_path):
    path = tmp_path / "memory.json"
    monkeypatch.setattr(memory, "MEMORY_FILE", str(path))

    result = memory.remember_memory(
        content="Акира — имя ассистента",
        kind="fact",
        key="assistant_identity",
    )

    assert result["success"] is True


def test_legacy_assistant_name_identity_preference_is_removed(monkeypatch, tmp_path):
    path = tmp_path / "memory.json"
    monkeypatch.setattr(memory, "MEMORY_FILE", str(path))
    data = _empty_memory()
    data["preferences"].append({
        "key": "Актуальный проект имени",
        "value": "Акира",
    })
    data["preferences"].append({
        "key": "preferred_name",
        "value": "Михаил",
    })
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    loaded = memory.load_memory()

    assert [item["value"] for item in loaded["preferences"]] == ["Михаил"]
    persisted = json.loads(path.read_text(encoding="utf-8"))
    assert [item["value"] for item in persisted["preferences"]] == ["Михаил"]
