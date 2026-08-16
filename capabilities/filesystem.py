"""Универсальный слой работы с файловой системой.

Безопасность:
- пути приводятся к абсолютным и разрешаются (включая symlink);
- доступ разрешён только внутри домашней папки пользователя;
- системные и служебные каталоги заблокированы;
- delete переносит объект в Корзину macOS, а не удаляет безвозвратно;
- rename принимает только простое имя без разделителей пути.
"""

import os
import shutil
from pathlib import Path

from config import MAX_FIND_LIMIT, MAX_READ_BYTES

from .protocol import fail, ok

HOME = Path.home()

BLOCKED_DIRS = (
    HOME / ".Trash",
    Path("/System"),
    Path("/Library"),
    Path("/etc"),
    Path("/usr"),
    Path("/bin"),
    Path("/sbin"),
    Path("/var"),
)

SKIP_DIR_NAMES = {".Trash", ".venv", "node_modules", ".git", "Library"}


class CapabilityError(Exception):
    """Ошибка валидации пути или аргументов capability."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def resolve_path(path, require_existing=False, must_be_file=False, must_be_dir=False):
    """Возвращает безопасный абсолютный Path или поднимает CapabilityError.

    Приводит к абсолютному пути, разрешает symlink и проверяет, что
    результат находится внутри домашней папки и не входит в заблокированные
    каталоги. Это закрывает path traversal (``..``) и symlink-побеги.
    """
    if not isinstance(path, str) or not path.strip() or "\x00" in path:
        raise CapabilityError("invalid_path", "Путь должен быть непустой строкой.")

    raw = os.path.expanduser(path.strip())

    if not os.path.isabs(raw):
        raise CapabilityError("not_absolute", "Требуется абсолютный путь: " + path)

    resolved = Path(raw).resolve()

    if not (resolved == HOME or HOME in resolved.parents):
        raise CapabilityError(
            "not_allowed",
            "Доступ разрешён только внутри домашней папки: " + str(resolved),
        )

    for blocked in BLOCKED_DIRS:
        if resolved == blocked or blocked in resolved.parents:
            raise CapabilityError(
                "blocked_directory",
                "Каталог заблокирован: " + str(resolved),
            )

    if require_existing and not resolved.exists():
        raise CapabilityError("not_found", "Путь не существует: " + str(resolved))

    if must_be_file and not resolved.is_file():
        raise CapabilityError("not_a_file", "Это не файл: " + str(resolved))

    if must_be_dir and not resolved.is_dir():
        raise CapabilityError("not_a_dir", "Это не каталог: " + str(resolved))

    return resolved


def _entry_info(path):
    try:
        stat = path.stat()
        size = stat.st_size
        mtime = int(stat.st_mtime)
        is_dir = path.is_dir()
    except OSError:
        size, mtime, is_dir = None, None, False

    return {
        "path": str(path),
        "name": path.name,
        "is_dir": is_dir,
        "size_bytes": size,
        "modified_at": mtime,
    }


def find(name, directory=None, limit=20, kind=None):
    """Ищет файлы и каталоги внутри домашней папки по части имени."""
    if not isinstance(name, str) or not name.strip():
        return fail("invalid_name", "name должен быть непустой строкой.")

    try:
        base = resolve_path(directory, must_be_dir=True) if directory else HOME
    except CapabilityError as error:
        return fail(error.code, str(error))

    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
        return fail("invalid_limit", "limit должен быть целым числом больше нуля.")

    limit = min(limit, MAX_FIND_LIMIT)
    query = name.lower()
    matches = []

    for root, dirs, files in os.walk(base):
        dirs[:] = [
            d for d in dirs
            if d not in SKIP_DIR_NAMES and not d.startswith(".")
        ]
        dirs.sort()

        entries = []

        if kind != "file":
            entries.extend(dirs)

        if kind != "dir":
            entries.extend(files)

        for entry in entries:
            if query in entry.lower():
                matches.append(_entry_info(Path(root) / entry))

                if len(matches) >= limit:
                    break

        if len(matches) >= limit:
            break

    return ok(
        {
            "matches": matches,
            "total": len(matches),
            "query": name,
            "directory": str(base),
            "limit": limit,
            "truncated": len(matches) >= limit,
        }
    )


def read(path, max_bytes=None):
    """Читает текстовый файл (UTF-8) с ограничением размера."""
    try:
        target = resolve_path(path, require_existing=True, must_be_file=True)
    except CapabilityError as error:
        return fail(error.code, str(error))

    if max_bytes is None:
        limit = MAX_READ_BYTES
    else:
        if not isinstance(max_bytes, int) or isinstance(max_bytes, bool) or max_bytes < 1:
            return fail("invalid_max_bytes", "max_bytes должен быть целым числом больше нуля.")

        limit = min(max_bytes, MAX_READ_BYTES)

    size = target.stat().st_size

    try:
        raw = target.read_bytes()
    except OSError as error:
        return fail("read_error", str(error), path=str(target))

    if len(raw) > limit:
        raw = raw[:limit]
        truncated = True
    else:
        truncated = False

    try:
        content = raw.decode("utf-8")
    except UnicodeDecodeError:
        return fail(
            "binary_file",
            "Файл не является текстовым (UTF-8).",
            path=str(target),
            size_bytes=size,
        )

    return ok(
        {
            "path": str(target),
            "content": content,
            "size_bytes": size,
            "truncated": truncated,
        }
    )


def write(path, content, append=False):
    """Записывает текст в файл, создавая родительские каталоги."""
    if not isinstance(content, str):
        return fail("invalid_content", "content должен быть строкой.")

    try:
        target = resolve_path(path)
    except CapabilityError as error:
        return fail(error.code, str(error))

    existed = target.exists()

    try:
        target.parent.mkdir(parents=True, exist_ok=True)

        if append:
            with open(target, "a", encoding="utf-8") as file:
                file.write(content)
        else:
            target.write_text(content, encoding="utf-8")
    except OSError as error:
        return fail("write_error", str(error), path=str(target))

    return ok(
        {
            "path": str(target),
            "bytes_written": len(content.encode("utf-8")),
            "append": bool(append),
            "existed": existed,
        }
    )


def create(path, kind="file", content=None, overwrite=False):
    """Создаёт новый файл или каталог."""
    if kind not in ("file", "dir"):
        return fail("invalid_kind", "kind должен быть file или dir.")

    try:
        target = resolve_path(path)
    except CapabilityError as error:
        return fail(error.code, str(error))

    if kind == "dir":
        if target.exists():
            return fail("already_exists", "Каталог уже существует: " + str(target))

        try:
            target.mkdir(parents=True)
        except OSError as error:
            return fail("create_error", str(error), path=str(target))

        return ok({"path": str(target), "kind": "dir"})

    if target.exists() and not overwrite:
        return fail("already_exists", "Файл уже существует: " + str(target))

    try:
        target.parent.mkdir(parents=True, exist_ok=True)

        if content is not None:
            target.write_text(str(content), encoding="utf-8")
        else:
            target.touch()
    except OSError as error:
        return fail("create_error", str(error), path=str(target))

    return ok(
        {
            "path": str(target),
            "kind": "file",
            "size_bytes": target.stat().st_size,
        }
    )


def _move_copy_precheck(src, dst):
    """Запрещает перемещение/копирование каталога внутрь самого себя."""
    if src.is_dir() and (dst == src or src in dst.parents):
        return fail(
            "invalid_destination",
            "Нельзя переместить каталог внутрь самого себя.",
        )

    return None


def move(source, destination):
    """Перемещает файл или каталог в новый путь."""
    try:
        src = resolve_path(source, require_existing=True)
        dst = resolve_path(destination)
    except CapabilityError as error:
        return fail(error.code, str(error))

    if dst.exists() and dst.is_dir():
        dst = dst / src.name

    precheck = _move_copy_precheck(src, dst)

    if precheck is not None:
        return precheck

    try:
        shutil.move(str(src), str(dst))
    except (OSError, shutil.Error) as error:
        return fail("move_error", str(error), source=str(src), destination=str(dst))

    return ok({"from": str(src), "to": str(dst), "is_dir": src.is_dir()})


def copy(source, destination):
    """Копирует файл или каталог в новый путь."""
    try:
        src = resolve_path(source, require_existing=True)
        dst = resolve_path(destination)
    except CapabilityError as error:
        return fail(error.code, str(error))

    if dst.exists() and dst.is_dir():
        dst = dst / src.name

    precheck = _move_copy_precheck(src, dst)

    if precheck is not None:
        return precheck

    try:
        if src.is_dir():
            shutil.copytree(str(src), str(dst))
        else:
            shutil.copy2(str(src), str(dst))
    except (OSError, shutil.Error) as error:
        return fail("copy_error", str(error), source=str(src), destination=str(dst))

    return ok({"from": str(src), "to": str(dst), "is_dir": src.is_dir()})


def rename(path, new_name):
    """Переименовывает файл или каталог в том же каталоге."""
    if not isinstance(new_name, str) or not new_name.strip():
        return fail("invalid_name", "new_name должен быть непустой строкой.")

    new_name = new_name.strip()

    if new_name in (".", "..") or "/" in new_name:
        return fail(
            "invalid_name",
            "new_name должен быть простым именем без разделителей пути.",
        )

    try:
        target = resolve_path(path, require_existing=True)
    except CapabilityError as error:
        return fail(error.code, str(error))

    destination = target.parent / new_name

    if destination.exists():
        return fail("already_exists", "Цель уже существует: " + str(destination))

    try:
        target.rename(destination)
    except OSError as error:
        return fail("rename_error", str(error), path=str(target))

    return ok({"from": str(target), "to": str(destination)})


def _trash_path(path):
    """Возвращает свободное имя в Корзине, не перезаписывая существующие."""
    trash = HOME / ".Trash"
    trash.mkdir(exist_ok=True)

    destination = trash / path.name
    counter = 1

    while destination.exists():
        destination = trash / (path.stem + " " + str(counter) + path.suffix)
        counter += 1

    return destination


def delete(path):
    """Перемещает файл или каталог в Корзину macOS (безвозвратно не удаляет)."""
    try:
        target = resolve_path(path, require_existing=True)
    except CapabilityError as error:
        return fail(error.code, str(error))

    if target == HOME:
        return fail("invalid_path", "Нельзя удалить домашнюю папку.")

    was_dir = target.is_dir()

    try:
        destination = _trash_path(target)
        shutil.move(str(target), str(destination))
    except (OSError, shutil.Error) as error:
        return fail("delete_error", str(error), path=str(target))

    return ok(
        {
            "path": str(target),
            "trash": str(destination),
            "is_dir": was_dir,
        }
    )
