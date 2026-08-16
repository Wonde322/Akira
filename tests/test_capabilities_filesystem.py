from pathlib import Path

import pytest


def _fs(isolated_project, monkeypatch, tmp_path):
    filesystem = isolated_project("capabilities.filesystem")
    monkeypatch.setattr(filesystem, "HOME", tmp_path)
    return filesystem


def test_find_returns_structured_matches_and_skips_hidden_dirs(
    isolated_project, monkeypatch, tmp_path
):
    fs = _fs(isolated_project, monkeypatch, tmp_path)

    visible = tmp_path / "documents" / "budget-2026.txt"
    visible.parent.mkdir()
    visible.write_text("data", encoding="utf-8")

    hidden = tmp_path / ".private" / "budget-secret.txt"
    hidden.parent.mkdir()
    hidden.write_text("data", encoding="utf-8")

    result = fs.find("budget")

    assert result["success"] is True
    assert result["data"]["total"] == 1
    assert result["data"]["matches"][0]["path"] == str(visible)
    assert result["data"]["matches"][0]["name"] == "budget-2026.txt"
    assert result["data"]["matches"][0]["size_bytes"] == 4


def test_find_filters_by_kind_and_directory(isolated_project, monkeypatch, tmp_path):
    fs = _fs(isolated_project, monkeypatch, tmp_path)

    (tmp_path / "projects").mkdir()
    (tmp_path / "projects" / "notes.md").write_text("x", encoding="utf-8")
    (tmp_path / "notes.md").write_text("x", encoding="utf-8")

    files = fs.find("notes.md", directory=str(tmp_path / "projects"), kind="file")

    assert files["data"]["total"] == 1
    assert files["data"]["matches"][0]["path"].endswith("projects/notes.md")

    dirs = fs.find("projects", kind="dir")

    assert dirs["data"]["total"] == 1
    assert dirs["data"]["matches"][0]["is_dir"] is True


def test_find_requires_valid_arguments(isolated_project, monkeypatch, tmp_path):
    fs = _fs(isolated_project, monkeypatch, tmp_path)

    assert fs.find("")["error"] == "invalid_name"
    assert fs.find("x", limit=0)["error"] == "invalid_limit"
    assert fs.find("x", limit="many")["error"] == "invalid_limit"
    assert fs.find("x", directory=str(tmp_path / "missing"))["error"] == "not_a_dir"


def test_read_returns_content_and_metadata(isolated_project, monkeypatch, tmp_path):
    fs = _fs(isolated_project, monkeypatch, tmp_path)

    target = tmp_path / "note.txt"
    target.write_text("привет, мир", encoding="utf-8")

    result = fs.read(str(target))

    assert result["success"] is True
    assert result["data"]["content"] == "привет, мир"
    assert result["data"]["path"] == str(target)
    assert result["data"]["size_bytes"] == len("привет, мир".encode("utf-8"))
    assert result["data"]["truncated"] is False


def test_read_rejects_binary_and_missing(isolated_project, monkeypatch, tmp_path):
    fs = _fs(isolated_project, monkeypatch, tmp_path)

    binary = tmp_path / "image.png"
    binary.write_bytes(b"\x89PNG\r\n\x1a\n")

    (tmp_path / "folder").mkdir()

    assert fs.read(str(binary))["error"] == "binary_file"
    assert fs.read(str(tmp_path / "missing.txt"))["error"] == "not_found"
    assert fs.read(str(tmp_path / "folder"))["error"] == "not_a_file"


def test_read_truncates_with_max_bytes(isolated_project, monkeypatch, tmp_path):
    fs = _fs(isolated_project, monkeypatch, tmp_path)

    target = tmp_path / "big.txt"
    target.write_text("x" * 1000, encoding="utf-8")

    result = fs.read(str(target), max_bytes=100)

    assert result["data"]["truncated"] is True
    assert result["data"]["content"] == "x" * 100
    assert result["data"]["size_bytes"] == 1000


def test_write_creates_parents_and_writes_content(isolated_project, monkeypatch, tmp_path):
    fs = _fs(isolated_project, monkeypatch, tmp_path)

    target = tmp_path / "a" / "b" / "file.txt"

    result = fs.write(str(target), "текст")

    assert result["success"] is True
    assert result["data"]["existed"] is False
    assert target.read_text(encoding="utf-8") == "текст"


def test_write_append_vs_overwrite(isolated_project, monkeypatch, tmp_path):
    fs = _fs(isolated_project, monkeypatch, tmp_path)

    target = tmp_path / "log.txt"

    fs.write(str(target), "one")
    fs.write(str(target), "two", append=True)

    assert target.read_text(encoding="utf-8") == "onetwo"

    fs.write(str(target), "three")

    assert target.read_text(encoding="utf-8") == "three"


def test_write_requires_string_content(isolated_project, monkeypatch, tmp_path):
    fs = _fs(isolated_project, monkeypatch, tmp_path)

    assert fs.write(str(tmp_path / "x.txt"), 42)["error"] == "invalid_content"


def test_create_file_and_dir(isolated_project, monkeypatch, tmp_path):
    fs = _fs(isolated_project, monkeypatch, tmp_path)

    created = fs.create(str(tmp_path / "new" / "file.txt"), content="data")

    assert created["success"] is True
    assert (tmp_path / "new" / "file.txt").read_text(encoding="utf-8") == "data"

    assert fs.create(str(tmp_path / "new" / "file.txt"))["error"] == "already_exists"

    assert fs.create(str(tmp_path / "folder"), kind="dir")["success"] is True
    assert (tmp_path / "folder").is_dir()

    assert fs.create(str(tmp_path / "folder"), kind="dir")["error"] == "already_exists"
    assert fs.create(str(tmp_path / "x"), kind="symlink")["error"] == "invalid_kind"


def test_create_overwrite_flag(isolated_project, monkeypatch, tmp_path):
    fs = _fs(isolated_project, monkeypatch, tmp_path)

    target = tmp_path / "f.txt"
    target.write_text("old", encoding="utf-8")

    fs.create(str(target), content="new", overwrite=True)

    assert target.read_text(encoding="utf-8") == "new"


def test_move_file_and_into_directory(isolated_project, monkeypatch, tmp_path):
    fs = _fs(isolated_project, monkeypatch, tmp_path)

    src = tmp_path / "src.txt"
    src.write_text("data", encoding="utf-8")
    dst = tmp_path / "dst.txt"

    result = fs.move(str(src), str(dst))

    assert result["success"] is True
    assert not src.exists()
    assert dst.read_text(encoding="utf-8") == "data"

    (tmp_path / "folder").mkdir()
    inside = tmp_path / "move.txt"
    inside.write_text("x", encoding="utf-8")

    fs.move(str(inside), str(tmp_path / "folder"))

    assert (tmp_path / "folder" / "move.txt").exists()


def test_move_dir_into_itself_is_rejected(isolated_project, monkeypatch, tmp_path):
    fs = _fs(isolated_project, monkeypatch, tmp_path)

    (tmp_path / "tree").mkdir()
    (tmp_path / "tree" / "sub").mkdir()

    result = fs.move(str(tmp_path / "tree"), str(tmp_path / "tree" / "sub" / "leaf"))

    assert result["error"] == "invalid_destination"


def test_copy_file_and_dir(isolated_project, monkeypatch, tmp_path):
    fs = _fs(isolated_project, monkeypatch, tmp_path)

    src = tmp_path / "src.txt"
    src.write_text("data", encoding="utf-8")
    dst = tmp_path / "copy.txt"

    result = fs.copy(str(src), str(dst))

    assert result["success"] is True
    assert src.exists()
    assert dst.read_text(encoding="utf-8") == "data"

    (tmp_path / "tree").mkdir()
    (tmp_path / "tree" / "leaf.txt").write_text("x", encoding="utf-8")

    copied = fs.copy(str(tmp_path / "tree"), str(tmp_path / "tree-copy"))

    assert copied["success"] is True
    assert (tmp_path / "tree-copy" / "leaf.txt").exists()


def test_rename_validates_new_name(isolated_project, monkeypatch, tmp_path):
    fs = _fs(isolated_project, monkeypatch, tmp_path)

    target = tmp_path / "old.txt"
    target.write_text("x", encoding="utf-8")

    result = fs.rename(str(target), "new.txt")

    assert result["success"] is True
    assert (tmp_path / "new.txt").exists()
    assert not target.exists()

    assert fs.rename(str(tmp_path / "new.txt"), "a/b")["error"] == "invalid_name"
    assert fs.rename(str(tmp_path / "new.txt"), "..")["error"] == "invalid_name"
    assert fs.rename(str(tmp_path / "new.txt"), "")["error"] == "invalid_name"


def test_delete_moves_to_trash_without_overwriting(isolated_project, monkeypatch, tmp_path):
    fs = _fs(isolated_project, monkeypatch, tmp_path)

    trash = tmp_path / ".Trash"
    trash.mkdir()

    first = tmp_path / "first" / "report.txt"
    first.parent.mkdir()
    first.write_text("first", encoding="utf-8")

    second = tmp_path / "second" / "report.txt"
    second.parent.mkdir()
    second.write_text("second", encoding="utf-8")

    result_first = fs.delete(str(first))
    result_second = fs.delete(str(second))

    assert result_first["success"] is True
    assert result_second["success"] is True

    assert not first.exists()
    assert not second.exists()

    assert (trash / "report.txt").read_text(encoding="utf-8") == "first"
    assert (trash / "report 1.txt").read_text(encoding="utf-8") == "second"


def test_delete_moves_directory_to_trash(isolated_project, monkeypatch, tmp_path):
    fs = _fs(isolated_project, monkeypatch, tmp_path)

    (tmp_path / "folder").mkdir()
    (tmp_path / "folder" / "file.txt").write_text("x", encoding="utf-8")

    result = fs.delete(str(tmp_path / "folder"))

    assert result["success"] is True
    assert result["data"]["is_dir"] is True
    assert not (tmp_path / "folder").exists()
    assert (tmp_path / ".Trash" / "folder" / "file.txt").read_text(encoding="utf-8") == "x"


def test_path_traversal_is_blocked(isolated_project, monkeypatch, tmp_path):
    fs = _fs(isolated_project, monkeypatch, tmp_path)

    result = fs.read(str(tmp_path / ".." / "escape.txt"))

    assert result["error"] == "not_allowed"


def test_relative_path_is_rejected(isolated_project, monkeypatch, tmp_path):
    fs = _fs(isolated_project, monkeypatch, tmp_path)

    assert fs.read("relative.txt")["error"] == "not_absolute"
    assert fs.write("../x", "y")["error"] == "not_absolute"


def test_symlink_escaping_home_is_blocked(isolated_project, monkeypatch, tmp_path):
    fs = _fs(isolated_project, monkeypatch, tmp_path)

    outside = tmp_path.parent / "outside_target"
    outside.mkdir()
    outside_file = outside / "secret.txt"
    outside_file.write_text("s", encoding="utf-8")

    link = tmp_path / "link.txt"
    link.symlink_to(outside_file)

    result = fs.read(str(link))

    assert result["error"] == "not_allowed"


def test_blocked_directories_are_rejected(isolated_project, monkeypatch, tmp_path):
    fs = _fs(isolated_project, monkeypatch, tmp_path)
    monkeypatch.setattr(fs, "BLOCKED_DIRS", (tmp_path / "private",))

    (tmp_path / "private").mkdir()

    result = fs.read(str(tmp_path / "private" / "x.txt"))

    assert result["error"] == "blocked_directory"


def test_absurd_path_values_are_rejected(isolated_project, monkeypatch, tmp_path):
    fs = _fs(isolated_project, monkeypatch, tmp_path)

    assert fs.read("")["error"] == "invalid_path"
    assert fs.read("\x00")["error"] == "invalid_path"
    assert fs.read(42)["error"] == "invalid_path"