def test_find_files_returns_matching_files_and_skips_hidden_directories(
    isolated_project, monkeypatch, tmp_path
):
    file_tools = isolated_project("file_tools")
    monkeypatch.setattr(file_tools, "HOME", tmp_path)

    visible = tmp_path / "documents" / "budget-2026.txt"
    visible.parent.mkdir()
    visible.write_text("data", encoding="utf-8")
    hidden = tmp_path / ".private" / "budget-secret.txt"
    hidden.parent.mkdir()
    hidden.write_text("data", encoding="utf-8")

    result = file_tools.find_files("budget")

    assert str(visible) in result
    assert str(hidden) not in result


def test_delete_file_moves_a_file_to_trash_without_overwriting_existing_name(
    isolated_project, monkeypatch, tmp_path
):
    file_tools = isolated_project("file_tools")
    monkeypatch.setattr(file_tools, "HOME", tmp_path)
    trash = tmp_path / ".Trash"
    trash.mkdir()

    first = tmp_path / "first" / "report.txt"
    first.parent.mkdir()
    first.write_text("first", encoding="utf-8")
    second = tmp_path / "second" / "report.txt"
    second.parent.mkdir()
    second.write_text("second", encoding="utf-8")

    assert file_tools.delete_file(str(first)) == "Файл перемещён в Корзину: report.txt"
    assert file_tools.delete_file(str(second)) == "Файл перемещён в Корзину: report.txt"

    assert not first.exists()
    assert not second.exists()
    assert (trash / "report.txt").read_text(encoding="utf-8") == "first"
    assert (trash / "report 1.txt").read_text(encoding="utf-8") == "second"


def test_delete_file_refuses_directories_and_missing_paths(
    isolated_project, monkeypatch, tmp_path
):
    file_tools = isolated_project("file_tools")
    monkeypatch.setattr(file_tools, "HOME", tmp_path)
    directory = tmp_path / "folder"
    directory.mkdir()

    assert file_tools.delete_file(str(directory)) == f"Это не файл: {directory}"
    assert file_tools.delete_file(str(tmp_path / "missing.txt")) == (
        f"Файл не найден: {tmp_path / 'missing.txt'}"
    )
