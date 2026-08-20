import json


def test_non_mapping_file_recovers_to_defaults(tmp_path, isolated_project):
    permissions = isolated_project("permissions")
    path = tmp_path / "permissions.json"
    path.write_text("[]", encoding="utf-8")
    manager = permissions.PermissionManager(path)
    assert manager._get() == permissions.DEFAULT_PERMISSIONS
    assert json.loads(path.read_text(encoding="utf-8")) == permissions.DEFAULT_PERMISSIONS


def test_invalid_json_recovers_and_persists_defaults(tmp_path, isolated_project):
    permissions = isolated_project("permissions")
    path = tmp_path / "permissions.json"
    path.write_text("{broken", encoding="utf-8")
    manager = permissions.PermissionManager(path)
    assert manager.get_permission("open") in {"auto", "confirm", "blocked"}
    assert json.loads(path.read_text(encoding="utf-8")) == permissions.DEFAULT_PERMISSIONS


def test_stale_tools_are_removed(tmp_path, isolated_project):
    permissions = isolated_project("permissions")
    path = tmp_path / "permissions.json"
    payload = permissions.DEFAULT_PERMISSIONS | {"removed_tool": "auto"}
    path.write_text(json.dumps(payload), encoding="utf-8")
    manager = permissions.PermissionManager(path)
    assert "removed_tool" not in manager._get()
    assert "removed_tool" not in json.loads(path.read_text(encoding="utf-8"))


def test_bad_level_falls_back_to_registry_default(tmp_path, isolated_project):
    permissions = isolated_project("permissions")
    path = tmp_path / "permissions.json"
    payload = permissions.DEFAULT_PERMISSIONS.copy()
    payload["open"] = "bogus"
    path.write_text(json.dumps(payload), encoding="utf-8")
    manager = permissions.PermissionManager(path)
    assert manager.get_permission("open") == permissions.DEFAULT_PERMISSIONS["open"]


def test_levels_are_normalized_for_case_and_space(tmp_path, isolated_project):
    permissions = isolated_project("permissions")
    path = tmp_path / "permissions.json"
    payload = permissions.DEFAULT_PERMISSIONS.copy()
    payload["open"] = " AUTO "
    path.write_text(json.dumps(payload), encoding="utf-8")
    manager = permissions.PermissionManager(path)
    assert manager.get_permission("open") == "auto"


def test_non_string_level_falls_back_to_default(tmp_path, isolated_project):
    permissions = isolated_project("permissions")
    path = tmp_path / "permissions.json"
    payload = permissions.DEFAULT_PERMISSIONS.copy()
    payload["open"] = ["auto"]
    path.write_text(json.dumps(payload), encoding="utf-8")
    manager = permissions.PermissionManager(path)
    assert manager.get_permission("open") == permissions.DEFAULT_PERMISSIONS["open"]


def test_unknown_tool_permission_can_be_saved_by_existing_manager_contract(tmp_path, isolated_project):
    permissions = isolated_project("permissions")
    path = tmp_path / "permissions.json"
    manager = permissions.PermissionManager(path)
    manager._get()
    assert manager.set_permission("does_not_exist", "auto") == "Для does_not_exist установлен уровень: auto"
    assert json.loads(path.read_text(encoding="utf-8"))["does_not_exist"] == "auto"


def test_valid_user_override_survives_normalization(tmp_path, isolated_project):
    permissions = isolated_project("permissions")
    path = tmp_path / "permissions.json"
    payload = permissions.DEFAULT_PERMISSIONS.copy()
    payload["open"] = "blocked"
    path.write_text(json.dumps(payload), encoding="utf-8")
    manager = permissions.PermissionManager(path)
    assert manager.get_permission("open") == "blocked"
    assert json.loads(path.read_text(encoding="utf-8"))["open"] == "blocked"